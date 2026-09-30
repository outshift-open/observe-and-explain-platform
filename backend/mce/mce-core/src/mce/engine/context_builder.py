#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Context Builder - Data Preparation for Metric Computation
========================================================
Extracts and organizes execution data into batches ready for metric computation.
Handles span extraction, batch grouping, and context updates.
"""

from __future__ import annotations

import logging
from typing import Any

from mce.core.metric import Metric

logger = logging.getLogger(__name__)

# Maps batch-type key (used throughout the engine) to the ontology URI it represents.
# Add an entry here when a new resource type (e.g. 'agent') is introduced.
BATCH_TYPE_TO_ONTOLOGY: dict[str, str] = {
    "session": "mas:Session",
    "llm": "mas:LLMCall",
    "tool": "mas:ToolCall",
}


def _with_resource_binding(
    base_context: dict[str, Any],
    resource_type: str,
    resource_node: dict[str, Any],
) -> dict[str, Any]:
    """Attach the current resource type/node to a compute context."""
    bound_context = base_context.copy()
    bound_context["resource_type"] = resource_type
    bound_context["resource_node"] = resource_node
    return bound_context


class ContextBuilder:
    """
    Prepares execution context and resource batches for metric computation.

    Responsibilities:
    - Extract spans from session context (LLM calls, tool calls)
    - Group resources by type (Session, LLMCall, ToolCall)
    - Filter resources by target_resource_id
    - Group metrics by applicability to resource types
    - Update contexts with computed metric results

    Usage:
        builder = ContextBuilder()
        batches = builder.build_resource_batches(context, session_id, recursive=True)
        grouped = builder.group_metrics_by_applicability(metrics, batches, recursive=True)
    """

    def build_resource_batches(
        self,
        context: dict[str, Any],
        session_id: str,
        recursive: bool = False,
        target_resource_id: str | None = None,
    ) -> dict[str, list[tuple[str, dict[str, Any]]]]:
        """
        Extract and organize resources into typed batches.

        Args:
            context: Session context from data provider
            session_id: Session identifier
            recursive: Include child resources (spans)
            target_resource_id: Filter to specific resource

        Returns:
            Dictionary with keys:
            - 'session': [(session_id, context)]
            - 'llm': [(span_id, span_context), ...]
            - 'tool': [(span_id, span_context), ...]
        """
        batches: dict[str, list[tuple[str, dict[str, Any]]]] = {
            t: [] for t in BATCH_TYPE_TO_ONTOLOGY
        }

        # Session batch (always included if not filtered out)
        if not target_resource_id or target_resource_id == session_id:
            session_node = context.get("session") or {}
            batches["session"].append(
                (
                    session_id,
                    _with_resource_binding(
                        context,
                        BATCH_TYPE_TO_ONTOLOGY["session"],
                        session_node,
                    ),
                )
            )

        # Extract spans (only if recursive)
        if not recursive:
            return batches

        raw_llm = context.get("llm_spans", [])
        raw_tool = context.get("tool_spans", [])

        # Fallback extraction if specific lists are missing
        if not raw_llm and not raw_tool:
            sess_obj = context.get("session")
            all_spans = getattr(sess_obj, "spans", []) if sess_obj else []

            if all_spans:
                raise ValueError(
                    "Session has spans but neither 'llm_spans' nor 'tool_spans' keys are "
                    "present in the context. The DataProvider must classify spans before "
                    "returning the context — add 'llm_spans' and 'tool_spans' lists."
                )

        # Prepare LLM batch
        batches["llm"] = self._prepare_spans(
            raw_llm,
            context,
            target_resource_id,
            BATCH_TYPE_TO_ONTOLOGY["llm"],
        )

        # Prepare Tool batch
        batches["tool"] = self._prepare_spans(
            raw_tool,
            context,
            target_resource_id,
            BATCH_TYPE_TO_ONTOLOGY["tool"],
        )

        logger.debug(
            f"Built batches: session={len(batches['session'])}, "
            f"llm={len(batches['llm'])}, tool={len(batches['tool'])}"
        )

        return batches

    def _prepare_spans(
        self,
        span_list: list[Any],
        base_context: dict[str, Any],
        target_resource_id: str | None,
        resource_type: str,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Convert span objects to (span_id, context) tuples.

        Args:
            span_list: List of span objects or dictionaries
            base_context: Base session context to merge with span data
            target_resource_id: Optional filter for specific span

        Returns:
            List of (span_id, enriched_context) tuples
        """
        result = []

        for span in span_list:
            # Convert span object to a plain dict.
            # Fix #18: __dict__ misses @property-backed attributes (Pydantic, dataclasses
            # with __slots__, OTel SDK objects).  Try model_dump() first (Pydantic v2),
            # then dict() (Pydantic v1), then vars(), then fall back to __dict__.
            if isinstance(span, dict):
                span_dict = span
            elif hasattr(span, "model_dump"):  # Pydantic v2
                span_dict = span.model_dump()
            elif hasattr(span, "dict"):  # Pydantic v1
                span_dict = span.dict()
            else:
                try:
                    span_dict = vars(span)
                except TypeError:
                    span_dict = getattr(span, "__dict__", {})

            # Extract span ID (try multiple property names)
            span_id = (
                span_dict.get("span_id")
                or span_dict.get("id")
                or span_dict.get("executionId")
            )

            if not span_id:
                logger.warning("Span without ID, skipping")
                continue

            # Filter by target
            if target_resource_id and span_id != target_resource_id:
                continue

            # Build enriched context (base + span-specific data)
            span_context = _with_resource_binding(
                base_context,
                resource_type,
                span_dict,
            )
            span_context.update(span_dict)

            result.append((span_id, span_context))

        return result

    def group_metrics_by_applicability(
        self,
        metrics: list[Metric],
        batches: dict[str, list[tuple[str, dict[str, Any]]]],
        recursive: bool = False,
        target_resource_id: str | None = None,
    ) -> dict[str, list[Metric]]:
        """
        Group metrics by the resource types they can operate on.

        Uses pre-resolved target_types from metric metadata (resolved at load time).

        Args:
            metrics: List of metrics to group
            batches: Resource batches from build_resource_batches()
            recursive: Whether to include span-level metrics

        Returns:
            Dictionary with keys 'session', 'llm', 'tool' mapping to applicable metrics
        """
        grouped = {t: [] for t in BATCH_TYPE_TO_ONTOLOGY}

        for metric in metrics:
            # Get pre-resolved target types from metadata
            targets = getattr(metric.metadata, "target_types", set())

            for batch_type, ontology_uri in BATCH_TYPE_TO_ONTOLOGY.items():
                if ontology_uri not in targets:
                    continue
                if not batches.get(batch_type):
                    continue
                # Span batches (llm, tool, …) require recursive mode
                if batch_type != "session" and not recursive:
                    continue
                grouped[batch_type].append(metric)

        logger.debug(
            "Grouped metrics: " + ", ".join(f"{t}={len(grouped[t])}" for t in grouped)
        )

        # Warn for every metric that was not routed to any batch, explaining why.
        routed_ids = {m.metric_id for t in grouped for m in grouped[t]}
        populated_batch_types = [t for t, batch in batches.items() if batch]
        available_uris = {BATCH_TYPE_TO_ONTOLOGY[t] for t in populated_batch_types}
        for metric in metrics:
            mid = getattr(metric, "metric_id", repr(metric))
            if mid in routed_ids:
                continue
            targets = getattr(getattr(metric, "metadata", None), "target_types", set())
            reasons: list[str] = []
            if not targets:
                reasons.append(
                    "no target_types resolved — check MetricScope or attachment_point"
                )
            else:
                overlap = targets & available_uris
                if not overlap:
                    reasons.append(
                        f"target_types {sorted(targets)} do not match any populated "
                        f"batch ({sorted(available_uris)})"
                    )
                else:
                    # Targets match but batch was filtered (e.g. recursive=False)
                    non_session_matches = [
                        uri for uri in overlap if uri != "mas:Session"
                    ]
                    if non_session_matches and not recursive:
                        reasons.append(
                            f"targets {non_session_matches} require recursive=True"
                        )
                    else:
                        reasons.append("batch matched but was empty or filtered")
            logger.warning(
                "Metric '%s' not routed to any batch — %s",
                mid,
                "; ".join(reasons),
            )

        return grouped

    def update_contexts_with_results(
        self, contexts: list[dict[str, Any]], results: list[Any]
    ) -> None:
        """Populate each context with the full list of computed results so far.

        VirtualMetrics read 'computed_metrics' to collect child values for
        aggregation.

        Fix #19: a reference to the *same* mutable list is stored in every
        context dict by design — VirtualMetrics read it after all base metrics
        in the current generation have appended their results, so the reference
        must remain live.  VirtualMetrics must treat the list as read-only
        during compute(); do NOT modify it inside compute().
        """
        for ctx in contexts:
            ctx["computed_metrics"] = results
