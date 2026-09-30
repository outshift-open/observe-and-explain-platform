#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
import json
import os
import atexit
import logging
from datetime import datetime, timezone
from pathlib import Path
from mce.core.types import MetricResult

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache storage backends.

    Subclasses **must** implement :meth:`get` and :meth:`store`.

    The batch primitives :meth:`get_batch`, :meth:`prefetch`, and :meth:`flush`
    have default implementations that delegate to single-item calls, so
    backends only need to override them for performance (e.g. one UNWIND
    query instead of N individual reads).

    Exposing these here ensures that any adapter replacing the Neo4j backend
    (e.g. an HTTP API server) implements the same batch contract without
    relying on duck-typing.
    """

    # ------------------------------------------------------------------ #
    # Required primitives                                                  #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def get(self, resource_id: str, metric_id: str) -> dict[str, Any] | None:
        """Return a cached result, or ``None`` if absent."""
        ...

    @abstractmethod
    def store(self, result: MetricResult) -> None:
        """Persist a single metric result (may be buffered until flush())."""
        ...

    # ------------------------------------------------------------------ #
    # Batch primitives — override for efficiency                           #
    # ------------------------------------------------------------------ #

    def get_batch(
        self, items: list[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Fetch multiple (resource_id, metric_id) pairs in one call.

        Default: delegates to :meth:`get` in a loop.  Override to issue a
        single batched query (e.g. one UNWIND to Neo4j or one POST to an
        API server).
        """
        hits: dict[tuple[str, str], dict[str, Any]] = {}
        for resource_id, metric_id in items:
            result = self.get(resource_id, metric_id)
            if result is not None:
                hits[(resource_id, metric_id)] = result
        return hits

    def prefetch(self, items: list[tuple[str, str]]) -> None:
        """Pre-warm the in-memory cache for a multi-session batch.

        Default: no-op.  Override to load all requested entries in one
        batched round-trip before the parallel :meth:`get_batch` calls
        begin (e.g. one UNWIND query or one bulk-fetch API call).
        """

    def flush(self) -> None:
        """Persist any buffered writes to the underlying store.

        Default: no-op.  Override when writes are buffered (e.g.
        :class:`KnowledgeGraphCache` accumulates results and writes them
        all at once via ``save_metrics()``; :class:`SessionMetricsCache`
        accumulates per-session dicts and writes one file per session).
        """


class JsonFileCache(CacheBackend):
    """
    File-based JSON cache backend.
    Useful for local development and preventing re-runs of expensive metrics.
    """

    def __init__(
        self, file_path: str, read_enabled: bool = True, write_enabled: bool = True
    ):
        self.file_path = file_path
        self.read_enabled = read_enabled
        self.write_enabled = write_enabled
        self._memory: dict[str, dict[str, Any]] = {}
        self._dirty: bool = False  # Fix #8: defer disk writes until flush()
        self._load()
        # Ensure in-memory state is always persisted on clean process exit.
        if write_enabled:
            atexit.register(self.flush)

    def _load(self):
        if not self.file_path:
            return
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                try:
                    self._memory = json.load(f)
                    logger.debug(f"Loaded metric cache from {self.file_path}")
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to load metric cache {self.file_path}: {e}")
                    self._memory = {}

    def _save(self):
        if not self.write_enabled or not self.file_path:
            return
        try:
            with open(self.file_path, "w") as f:
                json.dump(self._memory, f, indent=2)
            self._dirty = False
        except Exception as e:
            logger.error(f"Failed to save metric cache to {self.file_path}: {e}")

    def flush(self) -> None:
        """Persist any pending in-memory writes to disk.

        Fix #8: call this once after a batch of store() calls instead of
        relying on the per-item auto-save.  JsonFileCache.store() no longer
        calls _save() directly — it only marks the cache as dirty.
        """
        if self._dirty:
            self._save()

    def get(self, resource_id: str, metric_id: str) -> dict[str, Any] | None:
        if not self.read_enabled:
            return None
        if resource_id in self._memory and metric_id in self._memory[resource_id]:
            logger.debug(f"[READ] Cache Hit (JSON): {metric_id} for {resource_id}")
            return self._memory[resource_id][metric_id]
        return None

    def store(self, result: MetricResult) -> None:
        if not self.write_enabled:
            return

        if result.resource_id not in self._memory:
            self._memory[result.resource_id] = {}

        # Serialize result to dict
        res_dict = {
            "metric_id": result.metric_id,
            "resource_id": result.resource_id,
            "provider": result.provider,
            "value": result.value,
            "score": result.score,
            "reasoning": result.reasoning,
            "timestamp": result.timestamp.isoformat()
            if isinstance(result.timestamp, datetime)
            else str(result.timestamp),
            "metadata": result.metadata,
        }

        self._memory[result.resource_id][result.metric_id] = res_dict
        self._dirty = True  # Fix #8: mark dirty; actual disk write deferred to flush()
        logger.debug(
            f"[WRITE] Cached (JSON): {result.metric_id} for {result.resource_id}"
        )
        # Note: callers should invoke flush() after a batch to persist to disk.


class SessionMetricsCache(CacheBackend):
    """Per-session JSON cache for experiment artefacts.

    Mirrors exactly the benchmark run artefact structure::

        runs/
          {session_id}/
            metrics.json

    ``metrics.json`` content::

        {
          "GoalSuccessRate": {"score": 0.9, "reasoning": "...", "error": null,
                              "computed_at": "2026-...Z"},
          "Groundedness":    { ... },
          ...
        }

    Field ``score`` is aligned with the benchmark JSONL canonical format
    (``metrics/{metric_id}.jsonl``) so both artefact types can be consumed
    by the same analysis tooling.

    One file per session — identical layout to ``runs/{scenario}/{item}/{r}/``
    from the benchmark runner, so MCE pipeline artefacts are analysis-compatible
    with semantic-grouping runs.

    **Buffer + flush** write pattern (mirrors ``KnowledgeGraphCache``):
    ``store()`` accumulates into an in-memory buffer grouped by session;
    ``flush()`` writes exactly **one** ``metrics.json`` per dirty session.
    ``CacheManager.flush()`` calls this automatically at end of each batch.

    On init, all existing ``runs/*/metrics.json`` are loaded into an in-memory
    index for O(1) reads — no Neo4j round trips on subsequent runs.
    """

    def __init__(
        self,
        runs_dir: str | Path,
        read_enabled: bool = True,
        write_enabled: bool = True,
    ):
        self.runs_dir = Path(runs_dir)
        self.read_enabled = read_enabled
        self.write_enabled = write_enabled
        # (session_id, metric_id) → metric value dict (in-memory read index)
        self._data: dict[tuple[str, str], dict[str, Any]] = {}
        # session_id → {metric_id → rec}  (pending writes, flushed in flush())
        self._buffer: dict[str, dict[str, Any]] = {}
        self._load()
        if write_enabled:
            atexit.register(self.flush)

    def _load(self) -> None:
        """Load all existing runs/*/metrics.json into the in-memory index."""
        if not self.runs_dir.exists():
            return
        count = 0
        for path in sorted(self.runs_dir.glob("*/metrics.json")):
            session_id = path.parent.name
            try:
                with open(path, encoding="utf-8") as fh:
                    rec = json.load(fh)
                for metric_id, mdata in rec.items():
                    self._data[(session_id, metric_id)] = mdata
                    count += 1
            except (json.JSONDecodeError, OSError):
                continue
        if count:
            logger.debug(
                "[LOAD] SessionMetricsCache: %d entries loaded from %s",
                count,
                self.runs_dir,
            )

    # ------------------------------------------------------------------ #
    # CacheBackend interface                                               #
    # ------------------------------------------------------------------ #

    def get(self, resource_id: str, metric_id: str) -> dict[str, Any] | None:
        if not self.read_enabled:
            return None
        hit = self._data.get((resource_id, metric_id))
        if hit:
            logger.debug("[READ] Session cache hit: %s for %s", metric_id, resource_id)
        return hit

    def store(self, result: MetricResult) -> None:
        """Buffer result — actual disk write deferred to flush().

        All metrics for the same session accumulate in ``_buffer[session_id]``
        so that ``flush()`` writes exactly **one** file per session instead of
        N read-modify-write cycles (one per metric).
        """
        if not self.write_enabled:
            return
        session_id = result.resource_id
        rec: dict[str, Any] = {
            "score": getattr(result, "score", None)
            if getattr(result, "score", None) is not None
            else getattr(result, "value", None),
            "reasoning": getattr(result, "reasoning", ""),
            "error": getattr(result, "error", None),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._buffer.setdefault(session_id, {})[result.metric_id] = rec
        # Update read index immediately so subsequent get() calls in the same
        # batch see the buffered value without a disk read.
        self._data[(session_id, result.metric_id)] = rec

    def flush(self) -> None:
        """Write all buffered sessions to disk — one file per dirty session.

        Called automatically by ``CacheManager.flush()`` at end of each batch.
        Each session file is loaded from disk first so that previous metrics
        (written by an earlier run) are preserved.
        """
        if not self.write_enabled or not self._buffer:
            return
        written_sessions = 0
        written_metrics = 0
        for session_id, new_metrics in self._buffer.items():
            try:
                session_dir = self.runs_dir / session_id
                session_dir.mkdir(parents=True, exist_ok=True)
                metrics_path = session_dir / "metrics.json"
                existing: dict[str, Any] = {}
                if metrics_path.exists():
                    try:
                        with open(metrics_path, encoding="utf-8") as fh:
                            existing = json.load(fh)
                    except (json.JSONDecodeError, OSError):
                        pass
                existing.update(new_metrics)
                with open(metrics_path, "w", encoding="utf-8") as fh:
                    json.dump(existing, fh, indent=2)
                written_sessions += 1
                written_metrics += len(new_metrics)
            except Exception as exc:
                logger.warning(
                    "SessionMetricsCache flush failed for %s: %s", session_id, exc
                )
        logger.debug(
            "[FLUSH] SessionMetricsCache: %d metrics across %d sessions",
            written_metrics,
            written_sessions,
        )
        self._buffer.clear()

    def backfill_from_kg(self, entries: dict[tuple[str, str], dict[str, Any]]) -> int:
        """Populate local files from pre-fetched KG results (free — no LLM calls).

        Adds missing entries to the buffer and calls flush() so that each
        session gets exactly one file write (same path as normal store/flush).
        Entries already present in ``_data`` are skipped (idempotent).

        Returns the number of (session, metric) pairs written.
        """
        if not self.write_enabled:
            return 0

        added = 0
        for (session_id, metric_id), d in entries.items():
            if (session_id, metric_id) in self._data:
                continue
            rec: dict[str, Any] = {
                "score": d.get("score")
                if d.get("score") is not None
                else d.get("value"),
                "reasoning": d.get("reasoning", ""),
                "error": d.get("error"),
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }
            self._buffer.setdefault(session_id, {})[metric_id] = rec
            self._data[(session_id, metric_id)] = rec
            added += 1

        if added:
            logger.debug(
                "[BACKFILL] SessionMetricsCache: %d entries buffered from KG prefetch",
                added,
            )
            self.flush()
        return added


class KnowledgeGraphCache(CacheBackend):
    """
    Knowledge Graph cache backend — authoritative store for metric results.

    Read path  (read_enabled=True):  checks Neo4j before computing; a cache hit
                                     skips re-computation entirely.
    Write path (write_enabled=True): buffers results in memory during compute,
                                     then flushes them to Neo4j in one bulk
                                     save_metrics() call via flush().

    flush() is called automatically by CacheManager.flush() at the end of each
    compute() batch, so writes are always batched per session — never per metric.
    """

    def __init__(
        self,
        provider,
        read_enabled: bool = True,
        write_enabled: bool = True,
        flush_every: int = 0,
    ):
        """
        Args:
            flush_every:  Checkpoint flush interval (number of buffered results).
                          0 = no automatic flush (only explicit flush() calls).
                          > 0 = flush() is called automatically every time the
                          buffer reaches this size — useful to limit data loss
                          if a long batch crashes mid-way.
        """
        self.provider = provider
        self.read_enabled = read_enabled
        self.write_enabled = write_enabled
        self.flush_every = flush_every
        self._buffer: list[MetricResult] = []
        # Pre-warmed by prefetch() before a multi-session batch.  Keyed by
        # (resource_id, metric_id); checked first in get_batch() to avoid
        # per-session Neo4j round trips.
        self._prefetch: dict[tuple[str, str], dict] = {}

    def get(self, resource_id: str, metric_id: str) -> dict[str, Any] | None:
        """Single-item read — delegates to get_batch for consistency."""
        hits = self.get_batch([(resource_id, metric_id)])
        return hits.get((resource_id, metric_id))

    def prefetch(self, items: list[tuple[str, str]]) -> None:
        """Pre-warm the in-memory cache for all (resource_id, metric_id) pairs.

        Called ONCE before a multi-session batch to load all existing KG
        results in a SINGLE Neo4j query (one UNWIND with a IN filter for all
        metric_ids — the provider's get_metrics() already handles list mids).
        Subsequent get_batch() calls will find results here without hitting
        the database.
        """
        if not self.read_enabled or not self.provider:
            return

        all_rids = list({rid for rid, _ in items})
        all_mids = list({mid for _, mid in items})

        try:
            results = self.provider.get_metrics(all_rids, metric_ids=all_mids)
            for r in results:
                key = (r.resource_id, r.metric_id)
                self._prefetch[key] = {
                    "metric_id": r.metric_id,
                    "resource_id": r.resource_id,
                    "provider": getattr(r, "provider", "neo4j"),
                    "value": getattr(r, "value", 0.0),
                    "reasoning": getattr(r, "reasoning", ""),
                    "metadata": getattr(r, "metadata", {}),
                }
            logger.debug(
                "[PREFETCH] KG Cache: %d hits in 1 query (%d sessions × %d metrics)",
                len(results),
                len(all_rids),
                len(all_mids),
            )
        except Exception as e:
            logger.warning("KG Cache prefetch failed: %s", e)

    def get_batch(
        self, items: list[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Batch read: fetch all (resource_id, metric_id) pairs in one Neo4j call.

        Checks the prefetch dict first (populated by prefetch() before a
        multi-session batch).  Only items absent from the prefetch dict are
        queried against Neo4j — one UNWIND per metric_id.

        Returns a dict keyed by (resource_id, metric_id).
        """
        if not self.read_enabled:
            return {}

        # --- prefetch fast path ---
        hits: dict[tuple[str, str], dict[str, Any]] = {}
        missing: list[tuple[str, str]] = []
        for item in items:
            if item in self._prefetch:
                hits[item] = self._prefetch[item]
            else:
                missing.append(item)

        if not missing:
            if hits:
                logger.debug("[READ] KG prefetch hit: %d/%d", len(hits), len(items))
            return hits

        # --- DB fallback for anything not in prefetch ---
        if not self.read_enabled or not self.provider:
            return hits

        miss_rids = list({rid for rid, _ in missing})
        miss_mids = list({mid for _, mid in missing})
        missing_set = set(missing)

        try:
            results = self.provider.get_metrics(miss_rids, metric_ids=miss_mids)
            for r in results:
                key = (r.resource_id, r.metric_id)
                if key in missing_set:
                    hits[key] = {
                        "metric_id": r.metric_id,
                        "resource_id": r.resource_id,
                        "provider": getattr(r, "provider", "neo4j"),
                        "value": getattr(r, "value", 0.0),
                        "reasoning": getattr(r, "reasoning", ""),
                        "metadata": getattr(r, "metadata", {}),
                    }
        except Exception as e:
            logger.warning("KG Cache batch read failed: %s", e)

        if hits:
            logger.debug("[READ] KG Cache batch hit: %d/%d", len(hits), len(items))
        return hits

    def store(self, result: MetricResult) -> None:
        """Buffer the result in memory.  Actual Neo4j write happens in flush().

        When ``flush_every`` > 0, a checkpoint flush is triggered automatically
        every time the buffer reaches that size (e.g. ``flush_every=20`` with
        concurrency=4 × 5 metrics ≈ one checkpoint per concurrent wave).
        """
        if not self.write_enabled:
            return
        if getattr(result, "error", None) is not None:
            logger.debug(
                "[BUFFER] KG Cache: skipping errored result %s for %s",
                result.metric_id,
                result.resource_id,
            )
            return
        self._buffer.append(result)
        logger.debug(
            "[BUFFER] KG Cache: %s for %s", result.metric_id, result.resource_id
        )
        if self.flush_every > 0 and len(self._buffer) >= self.flush_every:
            logger.debug(
                "[CHECKPOINT] KG Cache: flushing %d results (flush_every=%d)",
                len(self._buffer),
                self.flush_every,
            )
            self.flush()

    def flush(self) -> None:
        """Bulk-write all buffered results to Neo4j in one save_metrics() call."""
        if not self.write_enabled or not self._buffer:
            return
        if not self.provider:
            logger.warning("KG Cache flush skipped: no provider")
            self._buffer.clear()
            return
        try:
            self.provider.save_metrics(self._buffer)
            logger.debug("[FLUSH] KG Cache: %d result(s) written", len(self._buffer))
        except Exception as e:
            logger.warning("KG Cache flush failed: %s", e)
        finally:
            self._buffer.clear()


class CacheManager:
    """
    Composite cache manager that delegates to a list of backends.
    """

    def __init__(self, backends: list[CacheBackend]):
        self.backends = backends

    def get(self, resource_id: str, metric_id: str) -> dict[str, Any] | None:
        """Single-item read — delegates to get_batch."""
        hits = self.get_batch([(resource_id, metric_id)])
        return hits.get((resource_id, metric_id))

    def prefetch(self, items: list[tuple[str, str]]) -> None:
        """Pre-warm all backends for a multi-session batch.

        Call once before the parallel compute loop; each backend decides
        whether to issue a bulk query or do nothing (default no-op).
        """
        for backend in self.backends:
            backend.prefetch(items)

    def get_batch(
        self, items: list[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, Any]]:
        """Batch read across all backends in priority order.

        Each backend is called with the items still missing from higher-
        priority backends.  Returns a merged dict keyed by
        (resource_id, metric_id).
        """
        hits: dict[tuple[str, str], dict[str, Any]] = {}
        remaining = list(items)

        for backend in self.backends:
            if not remaining:
                break
            batch_hits = backend.get_batch(remaining)
            hits.update(batch_hits)
            remaining = [it for it in remaining if it not in hits]

        return hits

    def store(self, result: MetricResult) -> None:
        """
        Store result in all capable backends.

        IMPORTANT: Virtual/aggregate metrics are NEVER cached.
        They depend on base metric results and should be recomputed each time.
        Caching them would risk stale data if base metrics change.
        """
        # Filter out virtual/aggregate metrics
        if self._is_virtual_metric(result):
            logger.debug(f"Skipping cache for virtual metric: {result.metric_id}")
            return

        for backend in self.backends:
            backend.store(result)

    def flush(self) -> None:
        """Flush all backends — one call drains all pending buffered writes."""
        for backend in self.backends:
            try:
                backend.flush()
            except Exception as e:
                logger.error("Cache flush failed for backend %r: %s", backend, e)

    def _is_virtual_metric(self, result: MetricResult) -> bool:
        """
        Check if a metric result came from a VirtualMetric and should not be cached.
        VirtualMetric.compute() always sets provider='virtual' — that is the
        canonical signal. No string-prefix heuristics needed.
        """
        return result.provider == "virtual"
