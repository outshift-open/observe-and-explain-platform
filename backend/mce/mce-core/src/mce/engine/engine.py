#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from copy import deepcopy
from typing import Any
import time
from datetime import datetime
from mce.core.types import MetricResult
from mce.core.metric import Metric, MetricRequirements, MetricNature
from mce.core.provider import DataProvider
from mce.providers.virtual.aggregators import VirtualMetric
from mce.core.registry.discovery import ensure_target_types  # Fix #11: top-level import
from .scheduler import TopologicalScheduler
from .strategies import (
    ExecutionStrategy,
    ThreadStrategy,
    ProcessStrategy,
    HybridStrategy,
    AsyncIOStrategy,
)
from .context_builder import ContextBuilder, BATCH_TYPE_TO_ONTOLOGY
import logging
from concurrent.futures import as_completed

logger = logging.getLogger(__name__)

# Ordered batch-type keys — derived from the single source of truth in context_builder.
BATCH_TYPES: tuple[str, ...] = tuple(BATCH_TYPE_TO_ONTOLOGY)


def _extend_unique(items: list[str], additions: list[str]) -> list[str]:
    for value in additions:
        if value not in items:
            items.append(value)
    return items


def _merge_requirements(
    base: MetricRequirements, req: MetricRequirements
) -> MetricRequirements:
    """Merge one metric requirement into the aggregated engine requirements.

    The engine must preserve semantic retrieval constraints in addition to the
    legacy field projections, otherwise DataProvider.fetch() falls back to an
    older, less specific code path.
    """
    _extend_unique(base.required_entities, req.required_entities)
    _extend_unique(base.text_fields, req.text_fields)
    _extend_unique(base.vector_fields, req.vector_fields)
    _extend_unique(base.scalar_fields, req.scalar_fields)
    _extend_unique(base.allowed_relations, req.allowed_relations)
    base.include_edges = base.include_edges or req.include_edges
    base.ground_truth = base.ground_truth or req.ground_truth

    if req.retrieval is None:
        return base

    if base.retrieval is None:
        base.retrieval = deepcopy(req.retrieval)
        return base

    retrieval = base.retrieval
    scope = retrieval.scope
    req_scope = req.retrieval.scope

    _extend_unique(scope.session_ids, req_scope.session_ids)
    _extend_unique(scope.resource_ids, req_scope.resource_ids)
    if scope.start_time is None:
        scope.start_time = req_scope.start_time
    if scope.end_time is None:
        scope.end_time = req_scope.end_time

    for node in req.retrieval.nodes:
        if node not in retrieval.nodes:
            retrieval.nodes.append(deepcopy(node))
    for edge in req.retrieval.edges:
        if edge not in retrieval.edges:
            retrieval.edges.append(deepcopy(edge))
    for aggregate in req.retrieval.aggregates:
        if aggregate not in retrieval.aggregates:
            retrieval.aggregates.append(deepcopy(aggregate))

    _extend_unique(retrieval.order_by, req.retrieval.order_by)
    if retrieval.limit is None or req.retrieval.limit is None:
        retrieval.limit = None
    else:
        retrieval.limit = max(retrieval.limit, req.retrieval.limit)

    return base


def _is_missing_context_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _context_list_item_key(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None

    for field in (
        "executionId",
        "sessionId",
        "spanId",
        "agentCallId",
        "llmCallId",
        "toolCallId",
        "transitionId",
        "stateId",
        "id",
    ):
        value = item.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"

    return None


def _merge_context_lists(
    current: list[Any],
    supplemental: list[Any],
) -> list[Any]:
    if not current:
        return deepcopy(supplemental)
    if not supplemental:
        return list(current)

    merged = [deepcopy(item) for item in current]
    keyed_indexes = {
        key: index
        for index, item in enumerate(merged)
        if (key := _context_list_item_key(item)) is not None
    }

    for supplemental_item in supplemental:
        key = _context_list_item_key(supplemental_item)
        if key is None or key not in keyed_indexes:
            if key is None:
                continue
            merged.append(deepcopy(supplemental_item))
            keyed_indexes[key] = len(merged) - 1
            continue

        current_item = merged[keyed_indexes[key]]
        if isinstance(current_item, dict) and isinstance(supplemental_item, dict):
            merged[keyed_indexes[key]] = _merge_missing_context_values(
                current_item,
                supplemental_item,
            )

    return merged


def _merge_missing_context_values(
    current: dict[str, Any],
    supplemental: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(current)

    for key, supplemental_value in supplemental.items():
        current_value = merged.get(key)

        if isinstance(current_value, dict) and isinstance(supplemental_value, dict):
            merged[key] = _merge_missing_context_values(
                current_value, supplemental_value
            )
            continue

        if isinstance(current_value, list) and isinstance(supplemental_value, list):
            merged[key] = _merge_context_lists(current_value, supplemental_value)
            continue

        if _is_missing_context_value(current_value) and not _is_missing_context_value(
            supplemental_value
        ):
            merged[key] = deepcopy(supplemental_value)

    return merged


class MetricEngine:
    """
    MCE v2 Core Engine.
    Manages metric registration, orchestration, and execution.
    """

    def __init__(
        self,
        max_workers: int = 4,
        execution_strategy: str | ExecutionStrategy = "hybrid",
    ):
        # Maps ontology_class -> list[Metric]
        self._registry: dict[str, list[Metric]] = {}
        # Secondary index: metric_id -> Metric for O(1) lookup via get_metric()
        self._by_id: dict[str, Metric] = {}
        self._data_provider: DataProvider | None = None

        # Scheduler
        self.scheduler = TopologicalScheduler()
        self._cache_manager = None
        # When True, compute() skips its per-call flush() so the caller
        # (compute_sessions_batch) can defer the single bulk flush to the end.
        self._defer_flush: bool = False
        self._requirements_cache: MetricRequirements | None = (
            None  # invalidated on register_metric
        )

        # Context Builder
        self._context_builder = ContextBuilder()

        self._sinks: list = []
        self._executor: ExecutionStrategy = self._create_executor(
            execution_strategy, max_workers
        )

    @staticmethod
    def _create_executor(
        strategy: str | ExecutionStrategy, max_workers: int
    ) -> ExecutionStrategy:
        """Factory: resolve a string strategy name to a concrete ExecutionStrategy."""
        if not isinstance(strategy, str):
            return strategy
        strategies = {
            "process": lambda: ProcessStrategy(max_workers),
            "thread": lambda: ThreadStrategy(max_workers),
            "asyncio": lambda: AsyncIOStrategy(),
        }
        return strategies.get(strategy, lambda: HybridStrategy(max_workers))()

    @property
    def _all_metrics(self) -> list[Metric]:
        """Flat list of all registered metrics across all ontology classes."""
        return [m for impls in self._registry.values() for m in impls]

    def set_data_provider(self, provider: DataProvider):
        self._data_provider = provider

    def set_cache_manager(self, cache_manager):
        """Set the caching manager for metric results."""
        self._cache_manager = cache_manager

    def add_sink(self, sink) -> None:
        """Register a storage sink. Sinks receive computed results via write()."""
        self._sinks.append(sink)

    def _dispatch_to_storage(self, results: list) -> None:
        """Write results to all registered sinks; exceptions are caught per-sink."""
        for sink in self._sinks:
            try:
                sink.write(results)
            except Exception as e:
                logger.warning("Storage sink %s failed: %s", sink, e)

    def shutdown(self):
        """Cleanup resources."""
        if hasattr(self._executor, "shutdown"):
            self._executor.shutdown(wait=True)

    def register_metric(self, metric: Metric) -> None:
        """Register a new metric plugin implementation.

        If the metric's ``metadata.target_types`` is empty, it is automatically
        populated from ``metadata.attachment_point`` (e.g. ``"mas:Session"``) so
        that the context builder can route it to the correct resource batch.
        """
        cls_name = metric.ontology_class
        if cls_name not in self._registry:
            self._registry[cls_name] = []

        # Ensure target_types is populated (single source of truth in discovery.py)
        # Fix #11: ensure_target_types now imported at module level — no inline import.
        ensure_target_types(metric)

        # Check for duplicates by metric_id
        for existing in self._registry[cls_name]:
            if existing.metric_id == metric.metric_id:
                logger.warning(
                    "Overwriting metric implementation: %s", metric.metric_id
                )
                self._registry[cls_name].remove(existing)
                break

        self._registry[cls_name].append(metric)
        self._by_id[metric.metric_id] = metric
        self._requirements_cache = None  # invalidate on registration
        logger.debug("Registered %s for %s", metric.metric_id, cls_name)

    def get_implementations(self, ontology_class: str) -> list[Metric]:
        return self._registry.get(ontology_class, [])

    def select_implementation(self, ontology_class: str) -> Metric | None:
        """Return the first registered implementation for *ontology_class*.

        Extensibility hook: override to implement context-aware selection.
        Fix #14: logs a warning when multiple implementations compete so the
        first-registered policy is auditable in production logs.
        """
        impls = self.get_implementations(ontology_class)
        if len(impls) > 1:
            logger.warning(
                "select_implementation('%s'): %d implementations registered; "
                "using first-registered '%s'. Override select_implementation() "
                "to change selection policy.",
                ontology_class,
                len(impls),
                impls[0].metric_id,
            )
        return impls[0] if impls else None

    def get_aggregated_requirements(self) -> MetricRequirements:
        """Calculate the minimal superset of data fields required by all metrics.

        Fix #13: result is cached after the first call and invalidated whenever
        a new metric is registered (register_metric clears _requirements_cache).
        """
        if self._requirements_cache is not None:
            return self._requirements_cache
        agg = MetricRequirements()
        for m in self._all_metrics:
            agg = _merge_requirements(agg, m.input_requirements)
        self._requirements_cache = agg
        return agg

    def _needs_session_base_context(
        self,
        requirements: MetricRequirements,
        metrics: list[Metric],
    ) -> bool:
        if requirements.retrieval is None:
            return False

        for metric in metrics:
            if isinstance(metric, VirtualMetric):
                continue

            metric_requirements = metric.input_requirements
            # Metrics without an explicit retrieval contract still depend on the
            # provider's canonical session payload. If we only fetch the aggregated
            # retrieval context contributed by another metric (for example
            # LLMErrorRate), polymorphic metrics like Duration or Cost can lose the
            # session node and the full LLMCall fields they read from implicitly.
            if metric_requirements.retrieval is None:
                return True

        return False

    def _fetch_session_base_context(
        self,
        session_id: str,
        requirements: MetricRequirements,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        if requirements.retrieval is None:
            return context

        session_requirements = deepcopy(requirements)
        session_requirements.retrieval = None
        base_context = self._data_provider.fetch(session_id, session_requirements)
        if not base_context:
            return context
        return _merge_missing_context_values(context, base_context)

    def compute_session(
        self,
        session_id: str,
        recursive: bool = False,
        target_resource_id: str | None = None,
        scope: str | None = None,
    ) -> list[MetricResult]:
        """
        Compute all registered metrics for a session.

        Simplified workflow:
        1. Fetch session context from data provider
        2. Build resource batches (session, llm spans, tool spans)
        3. Group metrics by applicability to resource types
        4. Execute metrics in dependency order (generations)
        5. Return all results

        Args:
            session_id: The ID of the session
            recursive: If True, compute metrics for child resources (spans, agents, etc.)
            target_resource_id: If set, restrict computation to this specific resource ID
            scope: Resource scope to compute on ('session', 'llm', 'tool', 'agent', 'task')

        Returns:
            List of all computed metric results
        """
        # Validate data provider
        if not self._data_provider:
            raise RuntimeError("No Data Provider set. Call set_data_provider() first.")

        # 1. Determine metrics and fetch session context
        all_metrics = self._all_metrics
        logger.debug("Fetching context for session %s...", session_id[:16])
        requirements = self.get_aggregated_requirements()
        context = self._data_provider.fetch(session_id, requirements)
        if self._needs_session_base_context(requirements, all_metrics):
            context = self._fetch_session_base_context(
                session_id, requirements, context
            )

        # 2. Build resource batches using ContextBuilder
        batches = self._context_builder.build_resource_batches(
            context,
            session_id,
            recursive=recursive,
            target_resource_id=target_resource_id,
        )

        # 3. Restrict batches to the requested scope. When aggregates are registered,
        # the session batch is retained so they can collect child results — but
        # base metrics are blocked from running on it later in _execute_generation.
        if scope is not None and scope != "session":
            has_aggregate = any(isinstance(m, VirtualMetric) for m in all_metrics)
            batches = self._filter_batches_by_scope(
                batches, scope, keep_session=has_aggregate
            )

        # 4. Group metrics by applicability
        grouped_metrics = self._context_builder.group_metrics_by_applicability(
            all_metrics,
            batches,
            recursive=recursive,
            target_resource_id=target_resource_id,
        )

        # 5. Execute generations in topological order
        computed_results: list[MetricResult] = []
        for generation in self._resolve_execution_order(all_metrics):
            self._execute_generation(
                generation, grouped_metrics, batches, computed_results, scope
            )

        # 6. Emit error MetricResults for metrics that produced no results at all.
        # This ensures callers always receive feedback explaining why a metric is
        # absent (scope mismatch, missing target_types, empty batches, etc.).
        computed_ids = {r.metric_id for r in computed_results if not r.error}
        available_uris = {
            uri for t, uri in BATCH_TYPE_TO_ONTOLOGY.items() if batches.get(t)
        }
        for metric in all_metrics:
            if metric.metric_id in computed_ids:
                continue
            targets = getattr(metric.metadata, "target_types", set())
            if not targets:
                reason = (
                    f"no target_types resolved for '{metric.metric_id}' — "
                    "check MetricScope or attachment_point in metadata"
                )
            elif not (targets & available_uris):
                reason = (
                    f"scope mismatch: '{metric.metric_id}' targets "
                    f"{sorted(targets)} but session only has "
                    f"{sorted(available_uris)}"
                )
            elif not recursive and (targets - {"mas:Session"}):
                reason = (
                    f"'{metric.metric_id}' targets non-session types "
                    f"{sorted(targets - {'mas:Session'})} — "
                    "pass recursive=True to enable span-level batches"
                )
            else:
                # Already has error results — skip duplicate
                if any(r.metric_id == metric.metric_id for r in computed_results):
                    continue
                reason = (
                    f"'{metric.metric_id}' produced no results — "
                    "no matching data found in this session"
                )
            computed_results.append(
                MetricResult(
                    metric_id=metric.metric_id,
                    resource_id=session_id,
                    provider=getattr(metric.metadata, "provider", "native"),
                    value=0.0,
                    error=reason,
                )
            )

        return computed_results

    def _execute_generation(
        self,
        generation: list[str],
        grouped_metrics: dict[str, list[Metric]],
        batches: dict[str, list],
        computed_results: list[MetricResult],
        scope: str | None,
    ) -> None:
        """Execute one topological generation across all batch types.

        Updates *computed_results* in-place.
        """
        logger.debug("Computing generation of %d metrics", len(generation))

        # Inject previously computed results into all contexts before running.
        for batch_type in BATCH_TYPES:
            for _, ctx in batches[batch_type]:
                self._context_builder.update_contexts_with_results(
                    [ctx], computed_results
                )

        for batch_type in BATCH_TYPES:
            applicable_metrics = [
                m for m in grouped_metrics[batch_type] if m.metric_id in generation
            ]
            # When a scope filter is active, the session batch is retained only
            # for VirtualMetrics (aggregates). Block base metrics from session.
            if scope is not None and scope != "session" and batch_type == "session":
                applicable_metrics = [
                    m for m in applicable_metrics if isinstance(m, VirtualMetric)
                ]

            if not applicable_metrics or not batches[batch_type]:
                continue

            resource_ids = [rid for rid, _ in batches[batch_type]]
            contexts = [ctx for _, ctx in batches[batch_type]]

            logger.debug(
                "  Batch %s: %d metrics x %d resources",
                batch_type,
                len(applicable_metrics),
                len(resource_ids),
            )
            # Fix #6: pass the pre-computed single-generation order to avoid a
            # redundant topological scheduling pass inside compute().
            result_map = self.compute(
                resource_ids,
                contexts,
                allowed_metrics=applicable_metrics,
                _presorted_generations=[[m.metric_id for m in applicable_metrics]],
            )
            for results in result_map.values():
                computed_results.extend(results)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _filter_batches_by_scope(
        self,
        batches: dict[str, list],
        scope: str,
        keep_session: bool,
    ) -> dict[str, list]:
        """Return a copy of *batches* containing only resources for *scope*.

        When *keep_session* is True the session batch is always retained so
        that VirtualMetrics (aggregates) can collect child results. Base
        metrics are subsequently blocked from running on it in the execution
        loop.
        """
        filtered: dict[str, list] = {t: [] for t in BATCH_TYPES}
        if scope in BATCH_TYPES:
            filtered[scope] = batches.get(scope, [])
        else:
            # 'agent' and 'task' scopes are not yet mapped to a batch type.
            # Fall back to session scope so the caller gets a result rather
            # than silent empty batches.
            logger.warning(
                "Scope %r has no corresponding batch type in %s. Falling back to 'session' scope.",
                scope,
                BATCH_TYPES,
            )
            filtered["session"] = batches.get("session", [])
        if keep_session:
            if scope != "session":
                # Only override when scope is different; avoids a redundant assignment.
                filtered["session"] = batches.get("session", [])
        logger.debug(
            "Scope %r: %d resources (session retained for aggregation: %s)",
            scope,
            sum(len(v) for v in filtered.values()),
            keep_session,
        )
        return filtered

    def get_metric(self, metric_id: str) -> Metric | None:
        """Retrieve a registered metric by its ID (O(1) lookup)."""
        return self._by_id.get(metric_id)

    def _resolve_execution_order(self, metrics: list[Metric]) -> list[list[str]]:
        """Delegates to Scheduler"""
        return self.scheduler.schedule(metrics)

    def _safe_execute_metric(self, metric, rids, contexts):
        """Execute *metric* over *rids*/*contexts* with cache read-through/write-through.

        Results are keyed by original index so ordering is always correct,
        regardless of whether compute_batch() returns fewer items than expected.
        """
        result_by_idx: dict[int, MetricResult] = {}
        non_cached: list[tuple[int, str, Any]] = []  # (orig_idx, rid, ctx)

        # Batch cache read — one round-trip for all (rid, metric_id) pairs.
        if self._cache_manager:
            batch_items = [(rid, metric.metric_id) for rid in rids]
            cache_hits = self._cache_manager.get_batch(batch_items)
        else:
            cache_hits = {}

        for i, (rid, ctx) in enumerate(zip(rids, contexts)):
            cached_entry = cache_hits.get((rid, metric.metric_id))
            if cached_entry:
                result_by_idx[i] = MetricResult(
                    metric_id=cached_entry["metric_id"],
                    resource_id=cached_entry["resource_id"],
                    provider=cached_entry.get("provider", "cache"),
                    value=cached_entry.get("value", 0.0),
                    reasoning=cached_entry.get("reasoning", ""),
                    metadata=cached_entry.get("metadata", {}),
                    error=None,
                )
            else:
                non_cached.append((i, rid, ctx))

        if non_cached:
            logger.debug(
                "[COMPUTE] Metric: %s  computed: %d/%d  (cache hits: %d)",
                metric.metric_id,
                len(non_cached),
                len(rids),
                len(rids) - len(non_cached),
            )
            batch_ts = datetime.now()  # uniform timestamp for the whole batch
            try:
                computed = metric.compute_batch(
                    [rid for _, rid, _ in non_cached],
                    [ctx for _, _, ctx in non_cached],
                )
            except Exception as exc:
                logger.error(
                    "compute_batch failed for metric %s: %s",
                    metric.metric_id,
                    exc,
                )
                for orig_i, rid, _ in non_cached:
                    result_by_idx[orig_i] = MetricResult(
                        metric_id=metric.metric_id,
                        resource_id=rid,
                        provider=getattr(metric.metadata, "provider", "native"),
                        value=0.0,
                        error=str(exc),
                    )
            else:
                for (orig_i, _, _), res in zip(non_cached, computed):
                    res.timestamp = batch_ts
                    result_by_idx[orig_i] = res
                    if self._cache_manager:
                        self._cache_manager.store(res)

        return [result_by_idx[i] for i in range(len(rids))]

    def compute(
        self,
        resource_ids: list[str],
        contexts: list[dict[str, Any]] | None = None,
        allowed_metrics: list[Metric] | None = None,
        *,
        _presorted_generations: list[list[str]] | None = None,
    ) -> dict[str, list[MetricResult]]:
        """
        Batch computation for multiple resources.

        Args:
            resource_ids: List of unique identifiers.
            contexts: Optional pre-fetched data. If None, DataProvider is used.
            allowed_metrics: Optional list of specific metrics to run. If None, all compatible registered metrics are candidates.

        Returns:
            Dictionary mapping resource_id -> list[MetricResult]
        """
        if not resource_ids:
            return {}

        start_time = time.time()
        logger.debug(
            "[BATCH] Starting batch computation for %d resources", len(resource_ids)
        )

        # 1. Fetch Data (Batch or Loop)
        fetch_start = time.time()
        if contexts is None:
            if self._data_provider:
                reqs = self.get_aggregated_requirements()
                try:
                    if hasattr(self._data_provider, "fetch_batch"):
                        contexts = self._data_provider.fetch_batch(resource_ids, reqs)
                    else:
                        # Fallback to loop
                        contexts = [
                            self._data_provider.fetch(rid, reqs) for rid in resource_ids
                        ]
                except Exception as e:
                    logger.error("Data Fetch Failed: %s", e)
                    raise RuntimeError(
                        f"Data provider failed to fetch batch: {e}"
                    ) from e
            else:
                contexts = [{} for _ in resource_ids]

        fetch_duration = time.time() - fetch_start
        logger.debug(
            "[BATCH] Data Fetch Phase completed in %.2fs (Avg: %.4fs/item)",
            fetch_duration,
            fetch_duration / len(resource_ids),
        )

        if len(contexts) != len(resource_ids):
            logger.error("Context count mismatch")
            return {rid: [] for rid in resource_ids}

        # 2. Select Metrics
        # Routing to the correct resource-type batch is handled inside
        # _execute_generation via group_metrics_by_applicability — all
        # registered metrics are candidates here; incompatible ones are
        # filtered per batch type later.
        selected_metrics = []

        # Candidates: either provided list or all registered
        if allowed_metrics is not None:
            selected_metrics = allowed_metrics
        else:
            selected_metrics = [
                m
                for cls_name in self._registry
                for m in [self.select_implementation(cls_name)]
                if m
            ]

        # 3. Resolve Schedule
        # Fix #6: when the caller has already computed the topological order
        # (e.g. _execute_generation), reuse it to avoid a redundant scheduling pass.
        generations = (
            _presorted_generations
            if _presorted_generations is not None
            else self._resolve_execution_order(selected_metrics)
        )
        results_map: dict[str, list[MetricResult]] = {rid: [] for rid in resource_ids}

        # Working Memory (mutable execution contexts)
        exec_contexts = [ctx.copy() for ctx in contexts]
        metric_map = {m.metric_id: m for m in selected_metrics}

        # 4. Execute Generations
        for generation in generations:
            gen_start = time.time()
            # Parallelize METRICS, where each metric processes the BATCH
            # This allows efficient batch-API usage (e.g. 1 call to OpenAI for 10 items)
            futures = {}
            for mid in generation:
                if mid not in metric_map:
                    continue
                metric = metric_map[mid]
                logger.debug(
                    "[BATCH] Scheduling metric %s for %d items", mid, len(resource_ids)
                )

                # Check execution strategy signature (does it support nature dispatch?)
                # All ExecutionStrategy implementations accept (fn, nature, *args).
                # Nature-based dispatch is handled internally by HybridStrategy;
                # ThreadStrategy and ProcessStrategy simply ignore it.
                nature = (
                    metric.nature
                    if hasattr(metric, "nature")
                    else MetricNature.DETERMINISTIC
                )
                fut = self._executor.submit(
                    self._safe_execute_metric,
                    nature,
                    metric,
                    resource_ids,
                    exec_contexts,
                )
                futures[fut] = mid

            for future in as_completed(futures):
                mid = futures[future]
                try:
                    batch_results = future.result()  # list[MetricResult]

                    for i, res in enumerate(batch_results):
                        # Store result
                        results_map[resource_ids[i]].append(res)

                        # Populate dependency context
                        # Note: Error results are skipped for dependency propagation
                        # Failed metrics won't populate context for dependent metrics
                        if res.error:
                            continue

                        exec_contexts[i][f"metric:{mid}"] = res
                        exec_contexts[i][f"metric:{mid}:value"] = res.value
                        exec_contexts[i][f"metric:{mid}:score"] = res.score

                except Exception as e:
                    logger.error("Critical failure in metric %s: %s", mid, e)

            gen_duration = time.time() - gen_start
            logger.debug(
                "[BATCH] Generation (%d metrics) completed in %.2fs",
                len(generation),
                gen_duration,
            )

        total_duration = time.time() - start_time
        logger.debug("[BATCH] Total batch processing time: %.2fs", total_duration)

        # Flush deferred writes once per batch — skipped when _defer_flush is
        # set by compute_sessions_batch() which handles the bulk flush itself.
        if self._cache_manager is not None:
            if not self._defer_flush:
                self._cache_manager.flush()

        return results_map

    def compute_all(
        self, resource_id: str, context: dict[str, Any] | None = None
    ) -> list[MetricResult]:
        """Single-item wrapper around compute()."""
        contexts = [context] if context is not None else None
        result_map = self.compute([resource_id], contexts)
        return result_map.get(resource_id, [])

    def compute_sessions_batch(
        self,
        session_ids: list[str],
        *,
        max_workers: int | None = None,
    ) -> dict[str, list[MetricResult]]:
        """Compute metrics for many sessions, batching both reads and writes.

        Performance vs N individual compute_session() calls:

        * **Reads**  : one ``prefetch()`` call before the loop — one Neo4j
          UNWIND query per metric_id across *all* sessions (6 queries for 6
          metrics regardless of how many sessions).
        * **Writes** : a single ``save_metrics()`` call at the very end via
          ``flush()`` (one Neo4j write for the entire batch).

        Args:
            session_ids: IDs of sessions to compute.
            max_workers: Thread-pool size for parallel session processing.  If
                         ``None``, the engine's default pool is used.

        Returns:
            Dict mapping session_id -> list[MetricResult].
        """
        import concurrent.futures

        if not session_ids:
            return {}

        # 1. Pre-warm cache: one UNWIND per metric_id across ALL sessions.
        if self._cache_manager is not None:
            metric_ids = [m.metric_id for m in self._all_metrics]
            prefetch_items = [(sid, mid) for sid in session_ids for mid in metric_ids]
            self._cache_manager.prefetch(prefetch_items)

        # 2. Compute every session; individual compute() calls skip their flush.
        self._defer_flush = True
        results: dict[str, list[MetricResult]] = {}
        workers = max_workers or getattr(self._executor, "max_workers", 4)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_sid = {
                    pool.submit(self.compute_session, sid): sid for sid in session_ids
                }
                for future in concurrent.futures.as_completed(future_to_sid):
                    sid = future_to_sid[future]
                    try:
                        results[sid] = future.result()
                    except Exception:
                        logger.exception(
                            "compute_sessions_batch: session %s failed", sid
                        )
                        results[sid] = []
        finally:
            self._defer_flush = False
            # 3. One bulk flush for the entire batch.
            if self._cache_manager is not None:
                self._cache_manager.flush()

        return results
