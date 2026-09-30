#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Compute Engine Setup Utilities

Functions for setting up the computation engine with proper configuration.
"""

from __future__ import annotations

import logging
import os
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


def setup_llm_service(cache_path: str, mode: str) -> None:
    """
    Configure LLM Service with caching.

    Args:
        cache_path: Path to LLM cache file
        mode: LLM interaction mode (live/record/replay/error)
    """
    from mce.engine.llm import LLMService, ErrorLLMService

    if mode.lower() == "error":
        LLMService._instance = ErrorLLMService()
        logger.debug("LLM: ERROR (any call will raise)")
        return
    LLMService.configure(
        cache_path=cache_path or os.getenv("MCE_LLM_CACHE_PATH", "llm_cache.json"),
        mode=mode.lower(),
        api_key=os.getenv("OPENAI_API_KEY") or None,
        model=os.getenv("MCE_LLM_MODEL") or "gpt-4o",
        base_url=(
            os.getenv("OPENAI_BASE_URL")
            or os.getenv("OPENAI_API_BASE")
            or os.getenv("LITELLM_BASE_URL")
            or None
        ),
    )

    if logger.isEnabledFor(logging.DEBUG):
        if mode.lower() == "record":
            logger.debug(f"LLM: RECORD -> {cache_path}")
        elif mode.lower() == "replay":
            logger.debug(f"LLM: REPLAY <- {cache_path}")
        elif mode.lower() == "live":
            logger.debug("LLM: LIVE (API)")


def setup_data_provider(
    file: str | None = None, legacy: bool = False, log_info: bool = False
):
    """
    Initialize appropriate data provider.
    MCE Core does not include providers by default.
    Depend on 'mce-client' if available, otherwise return None.
    """
    try:
        from mce.client.setup import setup_data_provider as setup

        return setup(file=file, legacy=legacy, log_info=log_info)
    except ImportError:
        logger.error(
            "No DataProvider configured. Install 'mce-client' package for default providers."
        )
        return None


def setup_cache_manager(
    kg_provider,
    no_cache_read: bool = False,
    no_cache_write: bool = False,
    flush_every: int = 0,
):
    """
    Setup the metric result cache backed by the Knowledge Graph.

    The KG is the authoritative cache store:
    - no_cache_read=True  skips KG read checks (forces full recomputation).
    - no_cache_write=True disables bulk writes at the end of each compute batch.

    Results are buffered in memory during computation and flushed to the KG in
    one bulk save_metrics() call per compute() invocation.

    Args:
        kg_provider:    KG provider instance (if None, caching is disabled).
        no_cache_read:  Disable reading from KG cache.
        no_cache_write: Disable writing to KG cache.
        flush_every:    Checkpoint flush interval (0 = manual only).  Passed
                        directly to KnowledgeGraphCache.

    Returns:
        CacheManager instance.
    """
    from mce.engine.caching import CacheManager, KnowledgeGraphCache

    cache_backends = []
    if kg_provider:
        cache_backends.append(
            KnowledgeGraphCache(
                kg_provider,
                read_enabled=not no_cache_read,
                write_enabled=not no_cache_write,
                flush_every=flush_every,
            )
        )
    return CacheManager(cache_backends)


def setup_engine(data_provider, cache_manager):
    """
    Create and configure MetricEngine with providers.

    Args:
        data_provider: Data provider instance
        cache_manager: Cache manager instance

    Returns:
        Configured MetricEngine instance
    """
    from mce.engine.engine import MetricEngine

    engine = MetricEngine()
    engine.set_data_provider(data_provider)
    engine.set_cache_manager(cache_manager)

    return engine


def parse_templated_metric(metric_expr: str) -> str:
    """
    Parse templated metric syntax and convert to metric_id.

    Supported syntaxes:
    - Aggregate<operation, metric> → operation_metric
    - Avg<metric> → avg_metric (shortcut for Aggregate<avg, metric>)
    - Max<metric> → max_metric (shortcut for Aggregate<max, metric>)
    - Min<metric> → min_metric (shortcut for Aggregate<min, metric>)
    - Sum<metric> → sum_metric (shortcut for Aggregate<sum, metric>)

    Examples:
        >>> parse_templated_metric("Aggregate<avg, AnswerRelevancy>")
        "avg_AnswerRelevancy"
        >>> parse_templated_metric("Avg<AnswerRelevancy>")
        "avg_AnswerRelevancy"
        >>> parse_templated_metric("ToolErrorRate")
        "ToolErrorRate"

    Args:
        metric_expr: Metric expression (templated or plain)

    Returns:
        Normalized metric_id
    """
    import re

    # Pattern 1: Aggregate<operation, metric>
    aggregate_pattern = r"^Aggregate<(\w+),\s*(\w+)>$"
    match = re.match(aggregate_pattern, metric_expr.strip())
    if match:
        operation, base_metric = match.groups()
        return f"{operation.lower()}_{base_metric}"

    # Pattern 2: Shortcut operations (Avg, Max, Min, Sum)
    shortcut_pattern = r"^(Avg|Max|Min|Sum)<(\w+)>$"
    match = re.match(shortcut_pattern, metric_expr.strip())
    if match:
        operation, base_metric = match.groups()
        return f"{operation.lower()}_{base_metric}"

    # No pattern matched: return as-is
    return metric_expr


def select_and_resolve_metrics(
    metric_names: list[str], compute_all: bool = False, log_info: bool = False
) -> tuple[list[Any], str]:
    """
    Select and resolve metrics from catalog with dependency resolution.

    Args:
        metric_names: List of metric names/IDs to compute
        compute_all: Compute all available metrics
        log_info: Log selection and resolution info

    Returns:
        Tuple of (selected_metrics, error_message)
        error_message is empty string if successful
    """
    from mce.core.registry import get_default_metrics

    default_metrics = get_default_metrics()
    selected_metrics = []

    # Expand comma-separated metric names and parse templated syntax
    expanded_metrics = []
    for m in metric_names:
        # First, check if it's a templated syntax (contains < or >)
        if "<" in m or ">" in m:
            # Don't split on comma - it's part of the template syntax
            normalized = parse_templated_metric(m.strip())
            expanded_metrics.append(normalized)
        else:
            # Plain metric name(s), safe to split on comma
            for metric_expr in m.split(","):
                normalized = parse_templated_metric(metric_expr.strip())
                expanded_metrics.append(normalized)

    if compute_all or "all" in expanded_metrics:
        selected_metrics = default_metrics
        if log_info:
            logger.warning(
                f"Computing ALL {len(default_metrics)} metrics "
                "(this may take time and cost money)"
            )
    else:
        # Select specific metrics with normalization
        for m_name in expanded_metrics:
            found = False
            from mce.core.types import normalize_metric_id

            m_name_normalized = normalize_metric_id(m_name)

            for dm in default_metrics:
                dm_id_normalized = normalize_metric_id(dm.metric_id)
                dm_ontology_normalized = normalize_metric_id(dm.ontology_class)

                if (
                    dm.metric_id == m_name
                    or dm.ontology_class == m_name
                    or dm_id_normalized == m_name_normalized
                    or dm_ontology_normalized == m_name_normalized
                ):
                    selected_metrics.append(dm)
                    found = True
                    break

            # Lazy loading fallback for templated aggregates
            if not found:
                from mce.core.catalog import MetricCatalogService

                catalog = MetricCatalogService.get_instance()
                lazy_metric = catalog.get_metric(m_name_normalized)
                if lazy_metric:
                    selected_metrics.append(lazy_metric)
                    found = True
                    logger.debug(
                        f"Lazy-loaded metric '{m_name_normalized}' via catalog"
                    )

            if not found:
                import click as _click

                _click.echo(
                    f"Warning: Metric '{m_name}' not found/registered.", err=True
                )
                logger.warning(f"Metric '{m_name}' not found/registered.")

    # Auto-include dependencies (BFS resolution)
    if selected_metrics:
        from mce.core.catalog import MetricCatalogService

        catalog = MetricCatalogService.get_instance()

        to_check: deque = deque(selected_metrics)
        checked_ids = {m.metric_id for m in selected_metrics}

        while to_check:
            current = to_check.popleft()
            for dep_id in getattr(current.metadata, "dependencies", []):
                if dep_id in checked_ids:
                    continue
                dep_impl = next(
                    (dm for dm in default_metrics if dm.metric_id == dep_id), None
                )
                if dep_impl:
                    if log_info:
                        logger.info(
                            f"Auto-including dependency: {dep_id} "
                            f"(required by {current.metric_id})"
                        )
                    selected_metrics.append(dep_impl)
                    to_check.append(dep_impl)
                    checked_ids.add(dep_id)
                else:
                    logger.warning(
                        f"Dependency '{dep_id}' for '{current.metric_id}' "
                        "not found in registry."
                    )

    if not selected_metrics:
        return [], "No valid metrics selected."

    return selected_metrics, ""
