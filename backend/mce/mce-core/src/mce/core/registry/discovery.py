#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Metric Discovery System
=======================
Dynamic discovery and resolution of metrics from various providers.
Handles versioning, ontology resolution, and provider enablement.

Migrated from providers/catalog_legacy.py (2026-02-18)
"""

from __future__ import annotations

from collections import defaultdict
import logging
import pkgutil
import importlib
import inspect
import threading
from importlib.metadata import entry_points

from packaging.version import parse as parse_version
from packaging.version import Version

import copy

from mce.core.metric import Metric
from mce.core.catalog import MetricCatalogService
from mce.core.metadata import MetricScope  # Fix #17 / #15

logger = logging.getLogger(__name__)

# Entry-point group name (same as telemetry-hub for cross-compatibility)
_PLUGIN_GROUP = "metrics_computation_engine.plugins"

# Module-level cache: None means "not yet computed", list means already computed.
_DISCOVERY_CACHE: list[Metric] | None = None
_DISCOVERY_LOCK = threading.Lock()

# Optional imports — not available in all environments
try:
    from oxp_ontology import OntologyService
except ImportError:
    OntologyService = None

if OntologyService is None:
    logger.debug(
        "ontology-service not available — ontology-based target_type resolution disabled; "
        "falling back to scope/attachment_point heuristics"
    )


# ============================================================================
# Version Management
# ============================================================================


def _get_metric_version(m: Metric) -> Version:
    """Extract version from metric metadata, default to 0.0.0 if not present."""
    try:
        if not hasattr(m, "metadata") or not hasattr(m.metadata, "version"):
            return parse_version("0.0.0")
        return parse_version(m.metadata.version)
    except (AttributeError, ValueError, TypeError):
        return parse_version("0.0.0")


def _filter_latest_versions(metrics: list[Metric]) -> list[Metric]:
    """
    Groups metrics by (provider, metric_id) and keeps only the highest version.

    Current behavior:
    - If multiple providers offer the same metric ID, they coexist
      (e.g. Ragas.Faithfulness vs DeepEval.Faithfulness).
    - If SAME provider offers multiple versions (Native.Foo v1 vs Native.Foo v2),
      keep latest only.
    """
    grouped = defaultdict(list)

    for m in metrics:
        provider = get_provider_name(m)
        key = (provider, m.metric_id)
        grouped[key].append(m)

    final_list = []
    for key, candidates in grouped.items():
        if len(candidates) == 1:
            final_list.append(candidates[0])
        else:
            # Sort by version descending, keep first (highest)
            candidates.sort(key=_get_metric_version, reverse=True)
            final_list.append(candidates[0])
            logger.debug(f"Filtered {len(candidates) - 1} older versions of {key}")

    return final_list


# ============================================================================
# Dynamic Discovery
# ============================================================================


def _discover_native_metrics(
    package_name: str = "mce.providers.native.metrics",
) -> list[Metric]:
    """
    Dynamically discovers all concrete Metric subclasses in the given package.

    Args:
        package_name: Python package path to scan for metrics

    Returns:
        List of instantiated metric objects
    """
    discovered = []
    try:
        package = importlib.import_module(package_name)
    except ImportError as e:
        logger.error(f"Could not import package {package_name}: {e}")
        return []

    if not hasattr(package, "__path__"):
        logger.warning(f"Package {package_name} has no __path__, skipping discovery")
        return []

    for _, name, _ in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        # Skip private / internal modules (e.g. _base.py)
        short_name = name.rsplit(".", 1)[-1]
        if short_name.startswith("_"):
            continue
        try:
            module = importlib.import_module(name)
            for _, obj in inspect.getmembers(module):
                # Check: class, Metric subclass, not Metric itself, defined in this package
                # Skip private/internal classes (name starts with '_')
                if (
                    inspect.isclass(obj)
                    and issubclass(obj, Metric)
                    and obj is not Metric
                    and not obj.__name__.startswith("_")
                    and obj.__module__.startswith(package_name)
                ):
                    if inspect.isabstract(obj):
                        continue

                    try:
                        # Instantiate with no arguments
                        discovered.append(obj())
                        logger.debug(f"Discovered metric: {obj.__name__}")
                    except TypeError as e:
                        # Skip metrics that require constructor arguments
                        logger.debug(
                            f"Skipping metric {obj.__name__} (requires arguments): {e}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Skipping metric {obj.__name__} (unexpected error during instantiation): {e}"
                        )

        except ImportError as e:
            logger.warning(f"Failed to import module {name} during discovery: {e}")

    logger.info(f"Discovered {len(discovered)} native metrics from {package_name}")
    return discovered


# ============================================================================
# Provider Management
# ============================================================================


def get_provider_name(m: Metric) -> str:
    """Return the provider name for a metric instance.

    Prefers the explicit ``metadata.provider`` field when non-empty; falls back
    to __module__ path inference so pre-existing metrics continue to work.
    """
    explicit = getattr(getattr(m, "metadata", None), "provider", "")
    if explicit and isinstance(explicit, str):
        return explicit
    mod = m.__class__.__module__
    if "deepeval" in mod:
        return "DeepEval"
    if "ragas" in mod:
        return "Ragas"
    if "opik" in mod:
        return "Opik"
    if "native" in mod:
        return "Native"
    if "sdk" in mod:
        return "SDK"
    if "virtual" in mod:
        return "Virtual"
    return "Other"


def ensure_target_types(m: Metric) -> None:
    """Populate *m.metadata.target_types* from attachment_point or MetricScope when empty.

    This is the single canonical implementation used by both
    ``_resolve_ontology_applicability()`` (during discovery) and
    ``MetricEngine.register_metric()`` (for manually registered metrics).
    Does nothing when ``target_types`` is already populated or when the metric
    has no metadata attribute (e.g. test stubs / MagicMock objects).
    """
    md = getattr(m, "metadata", None)
    if md is None:
        return
    if getattr(md, "target_types", None):
        return

    ap = getattr(md, "attachment_point", None)
    scope = getattr(md, "scope", None)
    scope_val = scope.value if hasattr(scope, "value") else str(scope)

    targets: set = set()
    # Fix #15: use enum values as the single source of truth for scope strings.
    # This survives future enum value renames without silent mismatches.
    if ap:
        targets.add(ap)
    elif scope_val == MetricScope.SESSION.value:
        targets.add("mas:Session")
    elif scope_val == MetricScope.SPAN.value:
        targets.update({"mas:LLMCall", "mas:ToolCall"})
    elif scope_val in (
        MetricScope.EXECUTION_ELEMENT.value,
        MetricScope.EXECUTION_ELEMENT.value.lower(),
    ):
        # ExecutionElement is the abstract base for the full execution chain.
        # Every subtype is included so polymorphic metrics (Duration, TokenCount…)
        # run on all node kinds. The engine is resilient: if a type is absent in
        # a given session the batch is simply empty.
        targets.update(
            {
                "mas:ExecutionElement",
                "mas:Session",
                "mas:MASCall",
                "mas:AgentCall",
                "mas:LLMCall",
                "mas:ToolCall",
            }
        )

    # Safe label for logging — works for Metric, MetricSpec, and test stubs.
    _label = getattr(m, "metric_id", None) or getattr(
        getattr(m, "metadata", None), "name", repr(m)
    )

    if targets:
        md.target_types = targets
        logger.debug("ensure_target_types %s → %s", _label, targets)
    else:
        logger.warning(
            "Could not resolve target_types for metric '%s' — scope=%s, attachment_point=%s. "
            "It will be skipped. Check MetricScope or set attachment_point explicitly.",
            _label,
            scope_val,
            ap,
        )


# ============================================================================
# Ontology Resolution
# ============================================================================


def _resolve_ontology_applicability(metrics: list[Metric]) -> list[Metric]:
    """
    Resolve each metric's applicability to ontology types based on attachment_point.
    Uses OntologyService when available; falls back to scope/attachment_point mapping.

    This always populates ``target_types`` so the engine never silently routes zero
    metrics.  Without this guarantee, a missing OntologyService would produce empty
    results with no error message.  The fallback mapping is intentionally conservative
    and covers 100 % of the current metric catalog.
    """
    onto = None
    if OntologyService is not None:
        try:
            onto = OntologyService.get_instance()
        except Exception as e:
            logger.error(
                "Could not initialize OntologyService: %s — using fallback routing", e
            )

    for m in metrics:
        # Guard against class-level MetricMetadata mutation: if the instance's
        # metadata IS the class attribute (shared across all instances), make an
        # instance-specific deep copy before writing to it.
        # Fix #3: walk the full MRO so inheritance chains are also guarded.
        class_metadata = next(
            (
                klass.__dict__["metadata"]
                for klass in type(m).__mro__
                if "metadata" in klass.__dict__
            ),
            None,
        )
        if class_metadata is not None and m.metadata is class_metadata:
            m.metadata = copy.deepcopy(m.metadata)

        md = m.metadata
        ap = md.attachment_point

        resolved = False
        if ap and onto is not None:
            try:
                targets = onto.get_subclasses_of(ap)
                md.target_types = targets
                logger.debug(
                    "Resolved %s applicability: %d types", m.metric_id, len(targets)
                )
                resolved = True
            except Exception as e:
                logger.error(
                    "Failed to resolve applicability for %s (AP=%s): %s",
                    m.metric_id,
                    ap,
                    e,
                )
                md.target_types = {ap}  # fallback: attachment point only
                resolved = True

        if not resolved:
            # OntologyService unavailable or no attachment_point — delegate to
            # the shared ensure_target_types helper (single source of truth).
            ensure_target_types(m)
            if getattr(md, "target_types", None):
                logger.debug(
                    "Fallback routing for %s (OntologyService=%s): %s",
                    m.metric_id,
                    "available" if onto else "unavailable",
                    md.target_types,
                )

    return metrics


# ============================================================================
# Main Discovery Function
# ============================================================================


def discover_all_metrics() -> list[Metric]:
    """
    Returns the full catalog of available metric instances.

    Results are memoized after the first call: the heavyweight package scan,
    external-provider imports, and ontology resolution only run once per
    process.  Call ``_reset_discovery_cache()`` in tests that need a fresh
    catalog.

    Discovery process:
    1. Discover modern metrics via MetricCatalogService
    2. Dynamically discover native MCE metrics
    3. Add SDK metrics (Duration, TokenCount, Cost)
    4. Conditionally import external providers (DeepEval, Ragas, Opik)
    5. Resolve ontology applicability for all metrics
    6. Filter to latest versions per provider

    Returns:
        List of metric instances ready for registration
    """
    global _DISCOVERY_CACHE
    if _DISCOVERY_CACHE is not None:
        return _DISCOVERY_CACHE

    with _DISCOVERY_LOCK:
        # Double-checked locking: another thread may have populated the cache
        # while we were waiting for the lock.
        if _DISCOVERY_CACHE is not None:
            return _DISCOVERY_CACHE

        logger.info("Starting metric discovery...")

        catalog = MetricCatalogService.get_instance()
        raw_metrics = []

        # 2. Native Metrics (Core MCE) - Dynamic Discovery
        discovered = _discover_native_metrics("mce.providers.native.metrics")
        raw_metrics.extend(discovered)

        # Add SDK metrics when the SDK provider wheel is installed.
        try:
            from mce.providers.sdk import DurationMetric, TokenCountMetric, CostMetric

            raw_metrics.extend([DurationMetric(), TokenCountMetric(), CostMetric()])
            logger.info("Added Native + SDK metrics")
        except ImportError as e:
            logger.warning(f"SDK provider enabled but import failed: {e}")

        # 3. Virtual Metrics
        # OPTION C: Lazy loading via catalog.get_metric() for "avg_*", "max_*", etc.
        # ALL avg_* metrics are now created on-demand via lazy loading (no pre-registration needed)
        logger.info("Added Virtual metrics (lazy loading enabled)")

        # 5. External Providers (Lazy Import)
        raw_metrics.extend(_discover_deepeval_metrics())
        raw_metrics.extend(_discover_ragas_metrics())
        raw_metrics.extend(_discover_opik_metrics())

        # 5b. Plugin Metrics (entry_points group: metrics_computation_engine.plugins)
        raw_metrics.extend(_discover_plugin_metrics())

        # 6. Resolve Ontology Applicability
        metrics = _resolve_ontology_applicability(raw_metrics)

        # 7. Filter to Latest Versions
        metrics = _filter_latest_versions(metrics)

        # 8. Back-fill catalog with the final metric list so that lazy-loading of
        #    virtual/aggregate metrics (e.g. avg_AnswerRelevancy) can find their
        #    base metrics in catalog._contracts.  External-provider metrics
        #    (DeepEval, Ragas, Opik) are collected into raw_metrics but never
        #    registered in the catalog — this step closes that gap.
        for m in metrics:
            if m.metric_id not in catalog._contracts:
                catalog.register_metric(m)

        # 9. Back-fill MetricRegistry so that MetricRegistry.get_all() returns the
        #    full discovered catalog — not just what was registered via load_provider().
        #    This unifies the three registries (MetricRegistry, MetricCatalogService,
        #    MetricEngine._registry) around the single source of truth produced here.
        from mce.core.registry.service import MetricRegistry

        registry = MetricRegistry.get_instance()
        for m in metrics:
            if registry.get_metric(m.metric_id) is None:
                registry.register(m)

        logger.info(f"Discovery complete: {len(metrics)} metrics available")
        _DISCOVERY_CACHE = metrics

    return _DISCOVERY_CACHE


# Backward-compatible alias (previously mce.providers.catalog.get_default_metrics)
get_default_metrics = discover_all_metrics


def _reset_discovery_cache() -> None:
    """Reset the discovery cache **and** all dependent singletons.

    Must be called under _DISCOVERY_LOCK to prevent races with concurrent
    discover_all_metrics() calls.
    """
    global _DISCOVERY_CACHE
    with _DISCOVERY_LOCK:
        _DISCOVERY_CACHE = None
        MetricCatalogService._instance = None
        from mce.core.registry.service import MetricRegistry

        MetricRegistry._instance = None


def _discover_deepeval_metrics() -> list[Metric]:
    """Discover DeepEval metrics when the package is importable."""

    try:
        from mce.providers.deepeval.wrapper import DeepEvalMetricWrapper

        metrics = [
            DeepEvalMetricWrapper(
                "AnswerRelevancy",
                {
                    "requirements": {
                        "aggregation_level": "execution_element",
                        "attachment_point": "mas:ExecutionElement",
                        "required_input_parameters": ["input_text", "output_text"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "Coherence",
                {
                    "requirements": {
                        "aggregation_level": "execution_element",
                        "attachment_point": "mas:ExecutionElement",
                        "required_input_parameters": ["output_text"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "Tonality",
                {
                    "requirements": {
                        "aggregation_level": "execution_element",
                        "attachment_point": "mas:ExecutionElement",
                        "required_input_parameters": ["input_text", "output_text"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "GeneralStructureAndStyle",
                {
                    "requirements": {
                        "aggregation_level": "execution_element",
                        "attachment_point": "mas:ExecutionElement",
                        "required_input_parameters": ["output_text"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "Toxicity",
                {
                    "requirements": {
                        "aggregation_level": "execution_element",
                        "attachment_point": "mas:ExecutionElement",
                        "required_input_parameters": ["input_text", "output_text"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "Bias",
                {
                    "requirements": {
                        "aggregation_level": "execution_element",
                        "attachment_point": "mas:ExecutionElement",
                        "required_input_parameters": ["input_text", "output_text"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "AnswerCorrectness",
                {
                    "requirements": {
                        "aggregation_level": "span",
                        "attachment_point": "mas:LLMCall",
                        "required_input_parameters": [
                            "input_text",
                            "output_text",
                            "expected_output",
                        ],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "Groundedness",
                {
                    "requirements": {
                        "aggregation_level": "span",
                        "attachment_point": "mas:LLMCall",
                        "required_input_parameters": [
                            "input_text",
                            "output_text",
                            "retrieval_context",
                        ],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "RoleAdherence",
                {
                    "requirements": {
                        "aggregation_level": "session",
                        "attachment_point": "mas:Session",
                        "required_input_parameters": ["conversation_data"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "ConversationCompleteness",
                {
                    "requirements": {
                        "aggregation_level": "session",
                        "attachment_point": "mas:Session",
                        "required_input_parameters": ["conversation_data"],
                    }
                },
            ),
            DeepEvalMetricWrapper(
                "TaskCompletion",
                {
                    "requirements": {
                        "aggregation_level": "session",
                        "attachment_point": "mas:Session",
                        "required_input_parameters": ["tool_spans", "input_query"],
                    }
                },
            ),
        ]
        logger.info(f"Added {len(metrics)} DeepEval metrics")
        return metrics
    except ImportError as e:
        logger.warning(f"DeepEval enabled but import failed: {e}")
        return []


def _discover_ragas_metrics() -> list[Metric]:
    """Discover Ragas metrics when the package is importable."""

    try:
        from mce.providers.ragas.adapter import RagasMetricWrapper

        metrics = [
            RagasMetricWrapper("Faithfulness", {"aggregation_level": "session"}),
            RagasMetricWrapper(
                "TopicAdherenceScore",
                {"aggregation_level": "session", "mode": "precision"},
            ),
        ]
        logger.info(f"Added {len(metrics)} Ragas metrics")
        return metrics
    except ImportError as e:
        logger.warning(f"Ragas enabled but import failed: {e}")
        return []


def _discover_opik_metrics() -> list[Metric]:
    """Discover Opik (Comet) metrics when the package is importable."""

    try:
        from mce.providers.opik.adapter import OpikMetricWrapper

        metrics = [
            OpikMetricWrapper(
                "Hallucination",
                {
                    "aggregation_level": "span",
                    "required_input_parameters": ["input_text", "output_text"],
                },
            ),
            OpikMetricWrapper(
                "Sentiment",
                {
                    "aggregation_level": "span",
                    "required_input_parameters": ["output_text"],
                },
            ),
        ]
        logger.info(f"Added {len(metrics)} Opik metrics")
        return metrics
    except ImportError as e:
        logger.warning(f"Opik enabled but import failed: {e}")
        return []


def _discover_plugin_metrics() -> list[Metric]:
    """Load external metric plugins registered via the entry_points system.

    Plugin packages declare their metrics using the ``metrics_computation_engine.plugins``
    entry-point group in their ``pyproject.toml``::

        [project.entry-points."metrics_computation_engine.plugins"]
        MyMetric = "my_package.module:MyMetricClass"

    Each registered class must be a **concrete** subclass of :class:`mce.core.metric.Metric`.
    Abstract classes and classes that raise on instantiation are silently skipped
    (a WARNING is emitted).

    This is the same entry-point group used by the telemetry-hub plugin ecosystem,
    ensuring cross-compatibility between both projects.
    """
    plugins: list[Metric] = []
    eps = entry_points(group=_PLUGIN_GROUP)
    for ep in eps:
        try:
            cls = ep.load()
            if not inspect.isclass(cls):
                logger.warning(
                    "Plugin entry-point %s is not a class, skipping", ep.name
                )
                continue
            if not issubclass(cls, Metric):
                logger.warning(
                    "Plugin %s (%s) does not subclass mce.core.metric.Metric, skipping",
                    ep.name,
                    cls,
                )
                continue
            if inspect.isabstract(cls):
                logger.debug("Plugin %s is abstract, skipping", ep.name)
                continue
            instance = cls()
            plugins.append(instance)
            logger.info("Loaded plugin metric: %s from %s", ep.name, ep.value)
        except Exception as exc:
            logger.warning("Plugin %s failed to load: %s", ep.name, exc)
    if plugins:
        logger.info("Loaded %d plugin metric(s) via entry_points", len(plugins))
    return plugins


def serialize_metric_catalog_format(m: "Metric", detailed: bool = False) -> dict:
    """Serialize a metric instance into the standard catalog JSON format.

    This function is the single source of truth for metric serialization.
    Previously lived in ``providers/catalog.py`` (now a compatibility shim).
    """
    md = m.metadata
    provider = get_provider_name(m)

    layer_val = md.layer.value if hasattr(md.layer, "value") else str(md.layer)
    scope_val = md.scope.value if hasattr(md.scope, "value") else str(md.scope)
    nature_val = md.nature.value if hasattr(md.nature, "value") else str(md.nature)

    doc = {
        "Name": md.name or m.metric_id,
        "Description": md.description,
        "Layer": layer_val,
        "Scope": scope_val,
        "Provider": provider,
        "MCE Implemented": "Yes",
        "Nature": nature_val,
        "Ontology Class": md.ontology_class,
        "Is Virtual": getattr(m, "is_virtual", False),
    }

    if detailed:
        doc.update(
            {
                "Status": (
                    "Available" if getattr(m, "is_available", True) else "Unavailable"
                ),
                "Version": getattr(md, "version", "N/A"),
                "Dependencies": getattr(m, "dependencies", []),
            }
        )

    return doc
