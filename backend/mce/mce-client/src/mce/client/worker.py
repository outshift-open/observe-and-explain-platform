#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCEWorkerService — declarative-config worker for metric computation.

This module is the canonical home of the worker.

Architecture
------------
The worker reads a declarative ``mce_config.yaml`` (validated against
``schema/worker_config.schema.yaml`` via Pydantic) that specifies:

- Which metrics to compute at each ontology scope (Session, LLMCall, ToolCall, …).
- Engine runtime parameters (max_workers, execution_strategy).
- Optional file-based cache configuration.

Scope keys follow the ontology class names so new scopes can be added without
any code changes — just add a new key to the ``metrics`` section of the YAML.

Single-pass strategy per session
---------------------------------
A single ``compute_session(recursive=True)`` call is made on a restricted
engine that only contains the metrics declared in the YAML config.  Per-node-
type routing is controlled by two things:

1. **YAML scope key** — determines *on which node types* the metric runs.
   ``ToolCall: [ToolError]`` means ToolError only fires on ``mas:ToolCall``
   nodes, never on Session or LLMCall nodes.  The scope key is translated to
   an ontology URI via :data:`_YAML_SCOPE_TO_ONTOLOGY_URI` and stored as the
   metric's ``target_types`` (a shallow copy so the global cache is not
   mutated).

2. **target_types fallback** — when a metric appears under an *unknown* scope
   key (no mapping in ``_YAML_SCOPE_TO_ONTOLOGY_URI``), its native
   ``target_types`` resolved from ``attachment_point`` / ``MetricScope`` are
   used unchanged.

Results are written to Neo4j in **one bulk write per batch**
(``process_batch``) or per session (``process_session``) to minimise round-trips.

Config location
---------------
Defaults to the ``default_worker_config.yaml`` bundled with this package.
Override with:
  - ``MCE_WORKER_CONFIG`` environment variable
  - Passing ``config_path`` explicitly to :class:`WorkerConfig` or
    :class:`MCEWorkerService`.
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from mce.engine.engine import MetricEngine

import yaml
from pydantic import BaseModel, Field, ValidationError

from .client import MCEClient
from .config import MCEClientConfig

logger = logging.getLogger(__name__)

# Bundled default config shipped with the package.
_BUNDLED_DEFAULT = Path(__file__).parent / "schema" / "default_worker_config.yaml"

# Maps YAML scope-key → the canonical ontology URI used as target_type.
# When a metric appears under a scope key in the YAML, its target_types are
# restricted to that URI — e.g. ToolError under ToolCall: runs only on
# mas:ToolCall nodes, never on mas:Session.
_YAML_SCOPE_TO_ONTOLOGY_URI: dict[str, str] = {
    "Session": "mas:Session",
    "MASCall": "mas:MASCall",
    "AgentCall": "mas:AgentCall",
    "LLMCall": "mas:LLMCall",
    "ToolCall": "mas:ToolCall",
    "TaskCall": "mas:TaskCall",
}


# ---------------------------------------------------------------------------
# Pydantic schema models (runtime validation)
# ---------------------------------------------------------------------------


class _EngineConfig(BaseModel):
    max_workers: int = Field(default=8, ge=1, le=64)
    execution_strategy: Literal["thread", "process", "hybrid", "asyncio"] = "hybrid"


class _CacheConfig(BaseModel):
    path: str | None = None
    read: bool = True
    write: bool = True


class _WorkerConfigSchema(BaseModel):
    """Internal Pydantic model — validates the raw YAML dict."""

    engine: _EngineConfig = Field(default_factory=_EngineConfig)
    cache: _CacheConfig = Field(default_factory=_CacheConfig)
    metrics: dict[str, list[str]] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# Public WorkerConfig
# ---------------------------------------------------------------------------


class WorkerConfig:
    """Loads and validates ``mce_config.yaml``.

    Validation is performed by :class:`_WorkerConfigSchema` (Pydantic).
    The JSON Schema file at ``schema/worker_config.schema.yaml`` is the
    authoritative documentation source and enables IDE auto-completion.

    Parameters
    ----------
    path:
        Path to the YAML file.  Resolution order:
        1. Explicit *path* argument.
        2. ``MCE_WORKER_CONFIG`` environment variable.
        3. Bundled ``default_worker_config.yaml`` shipped with the package.
    """

    #: Path to the JSON Schema for IDE support and documentation.
    SCHEMA_PATH: Path = Path(__file__).parent / "schema" / "worker_config.schema.yaml"

    def __init__(self, path: Path | str | None = None) -> None:
        config_path = Path(path or os.getenv("MCE_WORKER_CONFIG") or _BUNDLED_DEFAULT)
        self._path = config_path
        self._load(config_path)

    # ------------------------------------------------------------------
    # Loading & validation
    # ------------------------------------------------------------------

    def _load(self, path: Path) -> None:
        """Load and validate the YAML file, populating instance attributes."""
        if not path.exists():
            raise FileNotFoundError(
                f"Worker config not found: {path}\n"
                "Set MCE_WORKER_CONFIG or pass an explicit path."
            )
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}

        try:
            schema = _WorkerConfigSchema.model_validate(raw)
        except ValidationError as exc:
            lines = "\n".join(f"  • {e['loc']}: {e['msg']}" for e in exc.errors())
            raise ValueError(f"Invalid worker config at {path}:\n{lines}") from exc

        self.max_workers: int = schema.engine.max_workers
        self.execution_strategy: str = schema.engine.execution_strategy
        # Flexible scope dict — keys are ontology class names (Session, LLMCall, …)
        self.scope_metrics: dict[str, list[str]] = schema.metrics
        # Cache settings
        self.cache_path: str | None = schema.cache.path
        self.cache_read: bool = schema.cache.read
        self.cache_write: bool = schema.cache.write
        # Pre-computed frozen sets for fast membership checks per session
        self._session_metric_ids: frozenset[str] = frozenset(
            schema.metrics.get("Session", [])
        )
        self._element_metric_ids: frozenset[str] = frozenset(
            name
            for scope, names in schema.metrics.items()
            if scope != "Session"
            for name in names
        )
        # Pre-computed union used by the engine and compute loop.
        self.all_metric_ids: frozenset[str] = (
            self._session_metric_ids | self._element_metric_ids
        )

    @classmethod
    def validate_file(cls, path: Path | str) -> "_WorkerConfigSchema":
        """Validate a YAML file and return the parsed schema object.

        Raises :class:`ValueError` on validation failure.
        Used by the CLI ``validate-config`` command.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path) as fh:
            raw = yaml.safe_load(fh) or {}
        try:
            return _WorkerConfigSchema.model_validate(raw)
        except ValidationError as exc:
            lines = "\n".join(f"  • {list(e['loc'])}: {e['msg']}" for e in exc.errors())
            raise ValueError(f"Config validation failed:\n{lines}") from exc

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def session_metrics(self) -> list[str]:
        """Metrics for the Session scope (pass 1, non-recursive)."""
        return self.scope_metrics.get("Session", [])

    @property
    def element_metrics(self) -> list[str]:
        """Deduplicated union of all non-Session scope metrics (pass 2, recursive).

        Insertion order is preserved; duplicates across scopes are dropped.
        """
        seen: set[str] = set()
        result: list[str] = []
        for scope, names in self.scope_metrics.items():
            if scope == "Session":
                continue
            for name in names:
                if name not in seen:
                    seen.add(name)
                    result.append(name)
        return result

    @property
    def has_element_metrics(self) -> bool:
        """True when at least one non-Session scope metric is configured."""
        return bool(self._element_metric_ids)

    def to_dict(self) -> dict[str, Any]:
        """Serialise the effective configuration back to a plain dict."""
        return {
            "engine": {
                "max_workers": self.max_workers,
                "execution_strategy": self.execution_strategy,
            },
            "cache": {
                "path": self.cache_path,
                "read": self.cache_read,
                "write": self.cache_write,
            },
            "metrics": self.scope_metrics,
        }

    def __repr__(self) -> str:
        scopes = ", ".join(f"{k}={len(v)}" for k, v in self.scope_metrics.items())
        return f"WorkerConfig(path={self._path}, {scopes})"

    @property
    def path(self) -> Path:
        """The resolved config file path."""
        return self._path


# ---------------------------------------------------------------------------
# MCEWorkerService
# ---------------------------------------------------------------------------


class MCEWorkerService:
    """Dedicated Worker Service for Semantic Metric Computation.

    Instantiate once per worker process; the underlying Neo4j connection and
    engine are created lazily and reused across calls.

    Parameters
    ----------
    config_path:
        Path to the YAML configuration file.  Defaults to the bundled
        ``default_worker_config.yaml`` (see :class:`WorkerConfig`).
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        kg_provider: Any | None = None,
        client_config: MCEClientConfig | None = None,
        cache_read: bool | None = None,
        cache_write: bool | None = None,
    ) -> None:
        """Create a worker service.

        Parameters
        ----------
        config_path:
            Path to the YAML configuration file.  Defaults to the bundled
            ``default_worker_config.yaml`` (see :class:`WorkerConfig`).
        kg_provider:
            Optional pre-built KG provider injected directly into the client.
            When supplied, no Neo4j connection is created.  Useful for testing
            (pass a ``MockKGProvider``) or when the caller already holds a
            connected provider.
        client_config:
            Optional explicit client config. Use this when the worker should
            create its own Neo4j-backed provider without reading environment
            variables internally.
        cache_read:
            Optional override for cache reads. When provided, this takes
            precedence over the YAML config value.
        cache_write:
            Optional override for cache writes. When provided, this takes
            precedence over the YAML config value.
        """
        self._cfg = WorkerConfig(config_path)
        if cache_read is not None:
            self._cfg.cache_read = cache_read
        if cache_write is not None:
            self._cfg.cache_write = cache_write
        resolved_client_config = replace(
            client_config or MCEClientConfig(),
            engine_max_workers=self._cfg.max_workers,
            engine_strategy=self._cfg.execution_strategy,
        )
        self._client = MCEClient(
            config=resolved_client_config,
            kg_provider=kg_provider,
        )
        self._restricted_engine: MetricEngine | None = None  # Lazy
        scope_summary = ", ".join(
            f"{k}={len(v)}" for k, v in self._cfg.scope_metrics.items()
        )
        logger.info(
            "MCEWorkerService ready — %s | strategy=%s, max_workers=%d",
            scope_summary,
            self._cfg.execution_strategy,
            self._cfg.max_workers,
        )

    @property
    def config(self) -> WorkerConfig:
        """The resolved :class:`WorkerConfig` (read-only)."""
        return self._cfg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_metrics(self, resource_id: str) -> dict[str, Any]:
        """Fetch all computed metrics for a resource directly from the KG."""
        return self._client.get_metrics(resource_id=resource_id)

    def process_session(self, session_id: str) -> list[dict[str, Any]]:
        """Compute and store metrics for a single session.

        Results are persisted to Neo4j automatically via KnowledgeGraphCache.store()
        during engine computation.  No explicit save_metrics() call is needed.

        Returns a list of serialised :class:`~mce.core.types.MetricResult` dicts.
        """
        results, failed = self._compute_session_results(session_id)
        return [r.to_legacy_dict() for r in results + failed]

    def process_batch(self, session_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        """Compute metrics for multiple sessions with a single bulk KG write.

        Uses ``compute_sessions_batch()`` under the hood so that all N×3 per-
        session flushes are collapsed into one ``save_metrics()`` call at the
        very end — regardless of how many sessions or batch types are involved.

        Parameters
        ----------
        session_ids:
            Ordered list of session IDs to process.

        Returns
        -------
        Mapping from session_id → list of serialised metric result dicts
        (both passed and failed, matching :meth:`process_session` semantics).
        """
        if not session_ids or not self._cfg.all_metric_ids:
            return {sid: [] for sid in session_ids}

        engine = self._get_restricted_engine()
        logger.info(
            "[batch] Computing %d metrics across %d sessions (single flush)",
            len(self._cfg.all_metric_ids),
            len(session_ids),
        )

        # One bulk compute → one flush for the entire batch.
        raw_by_session = engine.compute_sessions_batch(session_ids)

        # Apply the same filtering as _compute_session_results().
        per_session: dict[str, tuple[list, list]] = {}
        for session_id in session_ids:
            raw = raw_by_session.get(session_id, [])
            passed, failed = [], []
            for r in raw:
                if r.metric_id not in self._cfg.all_metric_ids:
                    continue
                if r.error is not None:
                    logger.error(
                        "[%s] Metric %s failed: %s",
                        session_id[:8],
                        r.metric_id,
                        r.error,
                    )
                    failed.append(r)
                else:
                    passed.append(r)
            logger.debug(
                "[%s] → %d passed, %d failed", session_id[:8], len(passed), len(failed)
            )
            per_session[session_id] = (passed, failed)

        return {
            sid: [r.to_legacy_dict() for r in passed + failed]
            for sid, (passed, failed) in per_session.items()
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_restricted_engine(self) -> "MetricEngine":
        """Return a lazily-built engine restricted to the metrics declared in config.

        Each metric is registered with ``target_types`` narrowed to the exact
        ontology URIs declared in the YAML config.  For example::

            metrics:
              Session:  [Duration]     # runs only on mas:Session
              LLMCall:  [Duration]     # runs only on mas:LLMCall
              ToolCall: [ToolError]    # runs only on mas:ToolCall

        Without this restriction a metric whose spec declares
        ``scope=EXECUTION_ELEMENT`` (e.g. ``ToolError``) would be routed to
        every node type, including ``mas:Session``, even if the user only
        asked for it under ``ToolCall:``.

        A shallow copy of each metric (and its metadata) is made so the global
        discovery cache is never mutated.
        """
        if self._restricted_engine is None:
            from mce.engine.engine import MetricEngine
            from mce.core.registry.discovery import (
                discover_all_metrics,
                ensure_target_types,
            )

            # Build metric_id → YAML-declared ontology URIs.
            metric_yaml_uris: dict[str, set[str]] = {}
            for scope, names in self._cfg.scope_metrics.items():
                uri = _YAML_SCOPE_TO_ONTOLOGY_URI.get(scope)
                if uri is None:
                    logger.warning(
                        "Unknown YAML scope key '%s' — no ontology URI mapping. "
                        "Metrics listed here will use their native target_types.",
                        scope,
                    )
                    continue
                for name in names:
                    metric_yaml_uris.setdefault(name, set()).add(uri)

            engine = MetricEngine(
                max_workers=self._cfg.max_workers,
                execution_strategy=self._cfg.execution_strategy,
            )
            for metric in discover_all_metrics():
                if metric.metric_id not in self._cfg.all_metric_ids:
                    continue
                scoped = copy.copy(metric)
                scoped.metadata = copy.copy(metric.metadata)
                setattr(scoped, "_mce_max_workers", self._cfg.max_workers)
                ensure_target_types(metric)
                yaml_uris = metric_yaml_uris.get(metric.metric_id)
                if yaml_uris:
                    scoped.metadata.target_types = yaml_uris
                else:
                    scoped.metadata.target_types = copy.copy(
                        metric.metadata.target_types
                    )
                engine.register_metric(scoped)
            kg_provider = self._client._get_kg_provider()
            engine.set_data_provider(kg_provider)

            from mce.cli.helpers.compute_setup import setup_cache_manager

            cache_manager = setup_cache_manager(
                kg_provider,
                no_cache_read=not self._cfg.cache_read,
                no_cache_write=not self._cfg.cache_write,
            )
            engine.set_cache_manager(cache_manager)

            self._restricted_engine = engine
            logger.debug(
                "Restricted engine built with %d metrics: %s",
                len(self._cfg.all_metric_ids),
                sorted(self._cfg.all_metric_ids),
            )
        return self._restricted_engine

    def _compute_session_results(self, session_id: str) -> tuple[list, list]:
        """Run metric computation and return (passed, failed) results.

        A single ``compute_session(recursive=True)`` call is made on the
        restricted engine.  Per-node-type routing is handled by each metric's
        ``target_types`` (resolved from ``attachment_point`` / ``MetricScope``):

          - ``Session``        → fires once, on the Session node only
          - ``LLMCall``        → fires on every LLMCall in the session
          - ``ExecutionElement`` → fires on Session, AgentCall, LLMCall, ToolCall
          - etc.

        Results are filtered by the set of metric IDs declared in config so that
        metrics not requested (e.g. scope-mismatch error stubs emitted by the
        engine) are silently discarded.
        """
        if not self._cfg.all_metric_ids:
            return [], []

        engine = self._get_restricted_engine()

        logger.debug(
            "[%s] Computing %d metrics (recursive, target_types routing)",
            session_id[:8],
            len(self._cfg.all_metric_ids),
        )
        try:
            raw = engine.compute_session(session_id, recursive=True)
        except Exception:
            logger.exception("[%s] compute_session failed", session_id[:8])
            raise

        results: list = []
        failed: list = []
        for r in raw:
            if r.metric_id not in self._cfg.all_metric_ids:
                continue  # engine-emitted stub for a metric we didn't request
            if r.error is not None:
                logger.error(
                    "[%s] Metric %s failed: %s",
                    session_id[:8],
                    r.metric_id,
                    r.error,
                )
                failed.append(r)
            else:
                results.append(r)

        logger.debug(
            "[%s] → %d passed, %d failed", session_id[:8], len(results), len(failed)
        )
        return results, failed
