#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import importlib
import inspect
import pkgutil
import threading
import statistics
from mce.core.metric import Metric

logger = logging.getLogger(__name__)

# Lazy imports for heavy dependencies
try:
    from oxp_ontology import OntologyService
except ImportError:
    OntologyService = None


class MetricCatalogService:
    """
    Core Service: unified registry for Metric instances.
    Supports lazy creation of templated aggregate (virtual) metrics.
    """

    _instance = None
    _lock = threading.Lock()  # Guards singleton creation

    def __init__(self):
        self._contracts: dict[str, Metric | type[Metric]] = {}
        self._unified_metrics: dict[str, list[Metric]] = {}

    @classmethod
    def get_instance(cls):
        """Thread-safe singleton accessor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    cls._instance = MetricCatalogService()
        return cls._instance

    def register_metric(self, metric: Metric | type[Metric]) -> None:
        """Register a unified Metric plugin or abstract Base."""
        if isinstance(metric, type):
            # Abstract Class registration
            if not hasattr(metric, "metadata"):
                return  # Skip if no metadata
            mid = metric.metadata.name
            self._contracts[mid] = metric
            return

        # Instance registration
        mid = metric.metric_id
        if mid not in self._contracts:
            self._contracts[mid] = metric

        if mid not in self._unified_metrics:
            self._unified_metrics[mid] = []
        self._unified_metrics[mid].append(metric)

    def get_contract(self, metric_id: str) -> Metric | type[Metric] | None:
        """Look up a registered contract (or unified metric) by ID."""
        return self._contracts.get(metric_id)

    def get_metric(self, metric_id: str) -> Metric | None:
        """
        Get a unified metric instance.

        **Lazy Loading for Templated Aggregates** (Option C):
        If metric_id matches pattern "operation_BaseMetric" (e.g., "avg_AnswerRelevancy"),
        automatically create and cache an AggregateMetric instance.

        Supported operations:
        - avg_* → AverageMetric(base_metric)
        - max_* → AggregateMetric(base_metric, "max", max)
        - min_* → AggregateMetric(base_metric, "min", min)
        - sum_* → AggregateMetric(base_metric, "sum", sum)
        """
        # Check if already registered
        metrics = self._unified_metrics.get(metric_id, [])
        if metrics:
            return metrics[0]

        # Lazy loading: detect templated aggregate pattern
        operation_mapping = {
            "avg": ("avg", "AverageMetric"),
            "max": ("max", "max"),
            "min": ("min", "min"),
            "sum": ("sum", "sum"),
        }

        for prefix, (op_name, op_type) in operation_mapping.items():
            if metric_id.startswith(f"{prefix}_"):
                base_metric_id = metric_id[len(prefix) + 1 :]  # Remove "avg_" prefix

                # Validate base metric exists
                if base_metric_id not in self._contracts:
                    return None  # Base metric not found, cannot create aggregate

                # Import and instantiate appropriate aggregate metric
                if op_type == "AverageMetric":
                    from mce.providers.virtual.aggregators import AverageMetric

                    aggregate_metric = AverageMetric(target_metric_id=base_metric_id)
                else:
                    # max / min / sum operations
                    from mce.providers.virtual.aggregators import AggregateMetric

                    # Fix #20: statistics imported at module level
                    op_fn_map = {
                        "max": max,
                        "min": min,
                        "sum": sum,
                        "avg": statistics.mean,
                    }
                    aggregate_metric = AggregateMetric(
                        target_metric_id=base_metric_id,
                        operation_name=op_name,
                        operation_fn=op_fn_map[op_name],
                    )

                # Resolve target_types for the new metric
                self._resolve_target_types(aggregate_metric)

                # Register the lazily created metric
                self.register_metric(aggregate_metric)
                return aggregate_metric

        return None

    def _resolve_target_types(self, metric: "Metric") -> None:
        """Resolve target_types for a lazily created aggregate metric.

        Fix #16: delegates to the single source of truth in discovery.py
        (ensure_target_types) instead of duplicating the mapping logic here.
        The lazy import avoids the circular dependency
        (catalog → discovery → catalog).
        """
        from mce.core.registry.discovery import (
            ensure_target_types,
        )  # lazy — avoids circular import

        ensure_target_types(metric)

        # If ensure_target_types could not resolve (no scope/attachment_point),
        # fall back to ontology_class-based mapping for aggregate metrics which
        # inherit the base metric's class name rather than a MAS prefix.
        md = metric.metadata
        if not getattr(md, "target_types", None):
            ap = md.attachment_point
            if ap and OntologyService is not None:
                try:
                    onto = OntologyService.get_instance()
                    md.target_types = onto.get_subclasses_of(ap)
                    return
                except Exception as e:
                    logger.warning(
                        "OntologyService.get_subclasses_of(%r) failed: %s — "
                        "falling back to ontology_class mapping for '%s'.",
                        ap,
                        e,
                        md.name,
                    )
            # Last resort: map known ontology_class strings.
            _class_map = {
                "Session": {"mas:Session"},
                "LLMCall": {"mas:LLMCall"},
                "mas:LLMCall": {"mas:LLMCall"},
                "ToolCall": {"mas:ToolCall"},
                "mas:ToolCall": {"mas:ToolCall"},
            }
            md.target_types = _class_map.get(md.ontology_class, set())

    def get_all_contracts(self) -> list[Metric | type[Metric]]:
        return list(self._contracts.values())

    def discover_metrics(self, package_path: str = "mce.metrics"):
        """Auto-discover concrete Metric subclasses in the specified package."""
        try:
            module = importlib.import_module(package_path)
            path = getattr(module, "__path__", [])
            # NOTE: use module_name (not `name`) so the inner member loop cannot
            # shadow the outer iteration variable — that was a silent bug.
            # Fix #5: use walk_packages (recursive) instead of iter_modules (single-level)
            # so metrics in sub-packages are not silently dropped.
            for _, module_name, _ in pkgutil.walk_packages(
                path, prefix=f"{package_path}."
            ):
                sub_module = importlib.import_module(module_name)
                for member_name, obj in inspect.getmembers(sub_module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, Metric)
                        and obj is not Metric
                    ):
                        if inspect.isabstract(obj):
                            continue  # Skip abstract bases
                        try:
                            instance = obj()
                            self.register_metric(instance)
                        except Exception as e:
                            logger.warning(
                                "Failed to instantiate metric %s: %s", member_name, e
                            )
        except ImportError as e:
            logger.warning("Could not import package %s: %s", package_path, e)
