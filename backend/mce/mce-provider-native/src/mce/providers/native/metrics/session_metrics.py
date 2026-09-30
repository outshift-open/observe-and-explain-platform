#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Polymorphic Execution Metrics (KG-Based)

First-class metrics that apply to multiple ontology levels:
- Session (top-level execution)
- MASCall (multi-agent system execution)
- AgentCall (single agent execution)
- LLMCall (LLM invocation)
- ToolCall (tool invocation, limited metrics)

These metrics access node properties from the Knowledge Graph (Neo4j), not raw OTel spans.
The same metric name (e.g., Duration, Cost) computes appropriate values for each level.

Architecture Note:
- Metrics detect the resource type from context and resource_id
- Each node type may have different property names but similar semantics
- NO direct access to OTel spans (that's the adapters' job)
"""

from __future__ import annotations

import logging
from typing import Any

from mce.core.metric import (
    Metric,
    MetricLayer,
    MetricMetadata,
    MetricNature,
    MetricRequirements,
    MetricResult,
    MetricScope,
)
from mce.core.specs import SpecRegistry

# Constants
FLOAT_EPSILON = 1e-9  # For floating point comparisons

logger = logging.getLogger(__name__)

# Ontology types (for target_types)
TYPE_SESSION = "mas:Session"
TYPE_MAS_CALL = "mas:MASCall"
TYPE_AGENT_CALL = "mas:AgentCall"
TYPE_LLM_CALL = "mas:LLMCall"
TYPE_TOOL_CALL = "mas:ToolCall"


def _detect_resource_type(
    resource_id: str, context: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """
    Detect the resource type and extract the current node from context.

    ContextBuilder enriches context differently for each batch type:
    - Session batch: context = full session context
    - LLM/Tool batch: context = base_context enriched with span properties

    Args:
        resource_id: The resource ID being computed
        context: Metric computation context (varies by batch type)

    Returns:
        Tuple of (type_string, current_node_dict)

    Raises:
        ValueError: If resource type cannot be determined
    """
    explicit_type = context.get("resource_type")
    explicit_node = context.get("resource_node")
    if explicit_type:
        if explicit_node is None:
            raise ValueError(
                f"Resource node missing for {resource_id} ({explicit_type})"
            )
        return (explicit_type, explicit_node)

    # Check Session-level first
    session_id = context.get("session_id")
    if resource_id == session_id:
        session_node = context.get("session")
        if session_node is None:
            raise ValueError(f"Session node missing for {resource_id}")
        return (TYPE_SESSION, session_node)

    # Fallback: search in llm_spans and tool_spans lists
    return _search_spans_lists(resource_id, context)


def _search_spans_lists(
    resource_id: str, context: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """
    Search for resource_id in llm_spans and tool_spans lists.
    """
    llm_spans = context.get("llm_calls") or context.get("llm_spans", [])
    for llm_node in llm_spans:
        node_id = (
            llm_node.get("executionId") or llm_node.get("id") or llm_node.get("span_id")
        )
        if node_id == resource_id:
            return (TYPE_LLM_CALL, llm_node)

    tool_spans = context.get("tool_calls") or context.get("tool_spans", [])
    for tool_node in tool_spans:
        node_id = (
            tool_node.get("executionId")
            or tool_node.get("id")
            or tool_node.get("span_id")
        )
        if node_id == resource_id:
            return (TYPE_TOOL_CALL, tool_node)

    session_id = context.get("session_id")
    raise ValueError(
        f"Could not determine resource type for {resource_id}. "
        f"Context has session_id={session_id}, llm_spans={len(llm_spans)}, tool_spans={len(tool_spans)}"
    )


def _get_llm_calls(context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract LLMCall nodes from context.

    Args:
        context: Metric computation context

    Returns:
        List of LLMCall node dicts (may be empty)
    """
    return context.get("llm_calls") or context.get(
        "llm_spans", []
    )  # Note: "llm_spans" is the legacy context key for LLMCall nodes


def _get_tool_calls(context: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract ToolCall nodes from context.

    Args:
        context: Metric computation context

    Returns:
        List of ToolCall node dicts (may be empty)
    """
    return context.get("tool_calls") or context.get(
        "tool_spans", []
    )  # Note: "tool_spans" is the legacy context key for ToolCall nodes


def _extract_numeric_attribute(
    node: dict[str, Any], keys: list[str], default: float = 0.0
) -> float:
    """
    Extract a numeric attribute from a KG node, trying multiple key names.

    Args:
        node: KG node properties (dict)
        keys: List of attribute names to try (in order of preference)
        default: Default value if no key is found

    Returns:
        Numeric value or default
    """
    for key in keys:
        value = node.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            try:
                return float(stripped)
            except ValueError:
                continue
    return default


def _extract_numeric_attribute_with_source(
    node: dict[str, Any], keys: list[str], default: float = 0.0
) -> tuple[float, str | None]:
    """Extract a numeric attribute and report which key supplied the value."""
    for key in keys:
        value = node.get(key)
        if isinstance(value, (int, float)):
            return float(value), key
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                continue
            try:
                return float(stripped), key
            except ValueError:
                continue
    return default, None


class Duration(Metric):
    """
    Execution duration in milliseconds (polymorphic).

    Applies to: Session, MASCall, AgentCall, LLMCall, ToolCall

    Extracts duration from node properties in Knowledge Graph:
    - duration, durationMs (direct property)
    - startTime + endTime (calculated difference)

    Returns 0.0 if duration cannot be determined.
    """

    metadata = SpecRegistry.require("Duration").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements()

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        resource_type, current_node = _detect_resource_type(resource_id, context)

        # Try direct duration property
        duration = _extract_numeric_attribute(
            current_node, keys=["duration", "durationMs", "duration_ms"], default=0.0
        )

        # Fallback: Calculate from timestamps if available
        if duration < FLOAT_EPSILON:
            start = _extract_numeric_attribute(
                current_node, ["startTime", "start_time", "timestamp"], default=0.0
            )
            end = _extract_numeric_attribute(
                current_node, ["endTime", "end_time"], default=0.0
            )
            if start > 0 and end > 0:
                duration = (end - start) * 1000

        missing_data_error: str | None = None
        if duration < FLOAT_EPSILON:
            checked = ["duration", "durationMs", "duration_ms", "startTime+endTime"]
            present = [k for k in current_node if k in checked[:3]]
            missing_data_error = (
                f"Duration not found in KG node for {resource_type}: "
                f"checked {checked}, present keys: {present or 'none'}"
            )

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=float(duration),
            metric_class=self.ontology_class,
            reasoning=f"{resource_type.split(':')[1]} duration: {duration:.2f}ms",
            error=missing_data_error,
            metadata={
                "unit": "milliseconds",
                "resource_type": resource_type,
                "source": "kg_node_properties",
            },
        )


class TokenCount(Metric):
    """
    Token count for LLM operations (polymorphic).

    Applies to: Session, MASCall, AgentCall, LLMCall
    Returns 0 for: ToolCall (no tokens used)

    For aggregatable levels (Session/MAS/Agent), prefers precomputed totalTokens.
    If missing, aggregates from child LLMCall nodes recursively.

    For LLMCall, returns direct token count from node properties:
    - totalTokens (preferred)
    - inputTokens + outputTokens (fallback)

    KG Properties Used:
    - totalTokens, total_tokens, tokenCount
    - inputTokens + outputTokens (fallback calculation)
    """

    metadata = SpecRegistry.require("TokenCount").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements()

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        resource_type, current_node = _detect_resource_type(resource_id, context)

        # ToolCall: always return 0 (no tokens)
        if resource_type == TYPE_TOOL_CALL:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0,
                metric_class=self.ontology_class,
                reasoning="ToolCall does not use tokens",
                metadata={"resource_type": resource_type, "source": "n/a"},
            )

        # LLMCall: direct token count from node
        if resource_type == TYPE_LLM_CALL:
            total_tokens = _extract_numeric_attribute(
                current_node,
                keys=["totalTokenCount", "totalTokens", "total_tokens", "tokenCount"],
                default=0.0,
            )

            # Fallback: sum input + output
            if total_tokens < FLOAT_EPSILON:
                input_tokens = _extract_numeric_attribute(
                    current_node,
                    keys=[
                        "promptTokenCount",
                        "inputTokens",
                        "promptTokens",
                        "input_tokens",
                        "prompt_tokens",
                    ],
                    default=0.0,
                )
                output_tokens = _extract_numeric_attribute(
                    current_node,
                    keys=[
                        "completionTokenCount",
                        "outputTokens",
                        "completionTokens",
                        "output_tokens",
                        "completion_tokens",
                    ],
                    default=0.0,
                )
                total_tokens = input_tokens + output_tokens

            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=int(total_tokens),
                metric_class=self.ontology_class,
                reasoning=f"LLMCall tokens: {int(total_tokens)}",
                metadata={"resource_type": resource_type, "source": "kg_llm_node"},
            )

        # Session/MAS/Agent: prefer precomputed, fallback to aggregation
        llm_calls = _get_llm_calls(context)
        total_tokens = _extract_numeric_attribute(
            current_node,
            keys=["totalTokenCount", "totalTokens", "total_tokens", "tokenCount"],
            default=0.0,
        )

        source = "kg_precomputed"

        # Fallback: aggregate from LLMCall descendants
        if total_tokens < FLOAT_EPSILON:
            for llm_node in llm_calls:
                tokens = _extract_numeric_attribute(
                    llm_node,
                    keys=[
                        "totalTokenCount",
                        "totalTokens",
                        "total_tokens",
                        "tokenCount",
                    ],
                    default=0.0,
                )

                # If not available, sum input + output
                if tokens < FLOAT_EPSILON:
                    input_tokens = _extract_numeric_attribute(
                        llm_node,
                        keys=[
                            "promptTokenCount",
                            "inputTokens",
                            "promptTokens",
                            "input_tokens",
                            "prompt_tokens",
                        ],
                        default=0.0,
                    )
                    output_tokens = _extract_numeric_attribute(
                        llm_node,
                        keys=[
                            "completionTokenCount",
                            "outputTokens",
                            "completionTokens",
                            "output_tokens",
                            "completion_tokens",
                        ],
                        default=0.0,
                    )
                    tokens = input_tokens + output_tokens

                total_tokens += tokens
            source = "kg_llm_aggregation"

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=int(total_tokens),
            metric_class=self.ontology_class,
            reasoning=f"{resource_type.split(':')[1]} total tokens: {int(total_tokens)}",
            metadata={
                "resource_type": resource_type,
                "llm_call_count": len(llm_calls),
                "source": source,
            },
        )


class CallCount(Metric):
    """
    Total number of child calls (polymorphic).

    Applies to: Session, MASCall, AgentCall
    Not applicable to: LLMCall, ToolCall (leaf nodes, return 0)

    Counts LLMCall and ToolCall descendants from Knowledge Graph.
    Represents the total API calls/tool invocations under this execution scope.

    For Session: counts ALL LLMCall + ToolCall in session
    For MAS/Agent: counts LLMCall + ToolCall under that scope (future support)

    KG Properties Used:
    - Count of LLMCall nodes
    - Count of ToolCall nodes
    """

    metadata = SpecRegistry.require("CallCount").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements()

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        resource_type, _ = _detect_resource_type(resource_id, context)

        # Leaf nodes (LLMCall, ToolCall): no children, return 0
        if resource_type in (TYPE_LLM_CALL, TYPE_TOOL_CALL):
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0,
                metric_class=self.ontology_class,
                reasoning=f"{resource_type.split(':')[1]} is a leaf node (no child calls)",
                metadata={"resource_type": resource_type, "source": "n/a"},
            )

        # Aggregatable levels: count descendants
        llm_calls = _get_llm_calls(context)
        tool_calls = _get_tool_calls(context)

        llm_count = len(llm_calls)
        tool_count = len(tool_calls)
        total_calls = llm_count + tool_count

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=total_calls,
            metric_class=self.ontology_class,
            reasoning=f"{resource_type.split(':')[1]} child calls: {llm_count} LLM + {tool_count} Tool",
            metadata={
                "resource_type": resource_type,
                "llm_calls": llm_count,
                "tool_calls": tool_count,
                "source": "kg_descendant_counts",
            },
        )


class Cost(Metric):
    """
    Estimated cost in USD based on LLM token usage (polymorphic).

    Applies to: Session, MASCall, AgentCall, LLMCall
    Returns 0 for: ToolCall (no cost)

    Calculates cost from token usage using configured pricing model.
    Default pricing: GPT-4 baseline ($10/1M input, $30/1M output).

    For Session/MAS/Agent: aggregates cost from all descendant LLMCall nodes
    For LLMCall: calculates cost for single call
    For ToolCall: returns 0

    KG Properties Used:
    - inputTokens, promptTokens, input_tokens, prompt_tokens
    - outputTokens, completionTokens, output_tokens, completion_tokens

    Configuration:
    - Default pricing model: gpt-4
    - Future: load pricing from config based on model name

    Note: Baseline estimate - actual costs vary by model and provider.
    """

    def __init__(self, pricing_model: str = "gpt-4"):
        """Initialize with configurable pricing model (default: gpt-4)."""
        self.pricing_model = pricing_model
        self.metadata = MetricMetadata(
            name="Cost",
            description=f"Estimated cost in USD using {pricing_model} pricing (0 for ToolCall).",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.DETERMINISTIC,
            scope=MetricScope.EXECUTION_ELEMENT,  # Polymorphic
            ontology_class="Cost",
            version="1.0.0",
            target_types={
                TYPE_SESSION,
                TYPE_MAS_CALL,
                TYPE_AGENT_CALL,
                TYPE_LLM_CALL,
                TYPE_TOOL_CALL,
            },
        )

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements()

    @staticmethod
    def _llm_call_id(node: dict[str, Any]) -> str:
        return str(
            node.get("executionId") or node.get("id") or node.get("span_id") or "?"
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        resource_type, current_node = _detect_resource_type(resource_id, context)

        # ToolCall: always return 0 (no cost)
        if resource_type == TYPE_TOOL_CALL:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="ToolCall has no LLM cost",
                metadata={
                    "resource_type": resource_type,
                    "pricing_model": self.pricing_model,
                    "source": "n/a",
                },
            )

        # Pricing configuration (GPT-4 baseline)
        # Future enhancement: Load from config based on model name
        input_cost_per_1m = 10.0  # $10/1M input tokens
        output_cost_per_1m = 30.0  # $30/1M output tokens

        # LLMCall: single call cost
        if resource_type == TYPE_LLM_CALL:
            input_tokens, input_key = _extract_numeric_attribute_with_source(
                current_node,
                keys=[
                    "promptTokenCount",
                    "inputTokens",
                    "promptTokens",
                    "input_tokens",
                    "prompt_tokens",
                ],
                default=0.0,
            )
            output_tokens, output_key = _extract_numeric_attribute_with_source(
                current_node,
                keys=[
                    "completionTokenCount",
                    "outputTokens",
                    "completionTokens",
                    "output_tokens",
                    "completion_tokens",
                ],
                default=0.0,
            )

            input_cost = int(input_tokens) * input_cost_per_1m / 1_000_000
            output_cost = int(output_tokens) * output_cost_per_1m / 1_000_000
            total_cost = input_cost + output_cost

            logger.info(
                "Cost metric computed for %s %s: input_tokens=%s via %s, output_tokens=%s via %s, total_cost_usd=%.6f",
                resource_type,
                resource_id,
                int(input_tokens),
                input_key or "none",
                int(output_tokens),
                output_key or "none",
                total_cost,
            )

            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=round(total_cost, 6),
                metric_class=self.ontology_class,
                reasoning=f"LLMCall cost: ${total_cost:.6f} USD ({self.pricing_model})",
                metadata={
                    "resource_type": resource_type,
                    "input_tokens": int(input_tokens),
                    "output_tokens": int(output_tokens),
                    "input_cost_usd": round(input_cost, 6),
                    "output_cost_usd": round(output_cost, 6),
                    "pricing_model": self.pricing_model,
                    "source": "kg_llm_node",
                },
            )

        # Session/MAS/Agent: aggregate from LLMCall descendants
        llm_calls = _get_llm_calls(context)

        total_input_tokens = 0
        total_output_tokens = 0
        fallback_count = 0

        for llm_node in llm_calls:
            llm_call_id = self._llm_call_id(llm_node)
            input_tokens, input_key = _extract_numeric_attribute_with_source(
                llm_node,
                keys=[
                    "promptTokenCount",
                    "inputTokens",
                    "promptTokens",
                    "input_tokens",
                    "prompt_tokens",
                ],
                default=0.0,
            )

            output_tokens, output_key = _extract_numeric_attribute_with_source(
                llm_node,
                keys=[
                    "completionTokenCount",
                    "outputTokens",
                    "completionTokens",
                    "output_tokens",
                    "completion_tokens",
                ],
                default=0.0,
            )

            # WORKAROUND: if prompt/completion counts are both 0, estimate from
            # mas:totalTokenCount using a 70/30 input/output split.
            # This occurs when the LLM proxy reports only total_tokens (e.g. streaming).
            # Fix: ensure normalization writes non-zero promptTokenCount/completionTokenCount.
            # See: ingest_multi_layer_trajectory.py — promptTokenCount guard at line ~221.
            if input_tokens == 0.0 and output_tokens == 0.0:
                total_only, total_key = _extract_numeric_attribute_with_source(
                    llm_node,
                    keys=[
                        "totalTokenCount",
                        "totalTokens",
                        "total_tokens",
                        "tokenCount",
                    ],
                    default=0.0,
                )
                if total_only > 0.0:
                    fallback_count += 1
                    logger.warning(
                        "CostEfficiency WORKAROUND: LLMCall %s has promptTokenCount=0 and "
                        "completionTokenCount=0 but %s=%s. "
                        "Estimating 70/30 split. Fix normalization to write real token counts.",
                        llm_call_id,
                        total_key or "totalTokenCount",
                        int(total_only),
                    )
                    input_tokens = total_only * 0.7
                    output_tokens = total_only * 0.3
                    input_key = f"fallback:{total_key or 'totalTokenCount'}"
                    output_key = f"fallback:{total_key or 'totalTokenCount'}"

            logger.info(
                "Cost metric LLMCall %s under %s %s: input_tokens=%s via %s, output_tokens=%s via %s",
                llm_call_id,
                resource_type,
                resource_id,
                int(input_tokens),
                input_key or "none",
                int(output_tokens),
                output_key or "none",
            )

            total_input_tokens += int(input_tokens)
            total_output_tokens += int(output_tokens)

        input_cost = total_input_tokens * input_cost_per_1m / 1_000_000
        output_cost = total_output_tokens * output_cost_per_1m / 1_000_000
        total_cost = input_cost + output_cost

        if llm_calls and total_input_tokens == 0 and total_output_tokens == 0:
            logger.warning(
                "Cost metric produced zero tokens for %s %s despite %s descendant LLMCall nodes. Available keys per call: %s",
                resource_type,
                resource_id,
                len(llm_calls),
                {
                    self._llm_call_id(llm_node): sorted(llm_node.keys())
                    for llm_node in llm_calls
                },
            )

        logger.info(
            "Cost metric computed for %s %s: llm_call_count=%s, total_input_tokens=%s, total_output_tokens=%s, fallback_count=%s, total_cost_usd=%.6f",
            resource_type,
            resource_id,
            len(llm_calls),
            total_input_tokens,
            total_output_tokens,
            fallback_count,
            total_cost,
        )

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=round(total_cost, 6),
            metric_class=self.ontology_class,
            reasoning=f"{resource_type.split(':')[1]} cost: ${total_cost:.6f} USD ({self.pricing_model})",
            metadata={
                "resource_type": resource_type,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "input_cost_usd": round(input_cost, 6),
                "output_cost_usd": round(output_cost, 6),
                "pricing_model": self.pricing_model,
                "source": "kg_llm_aggregation",
                "llm_call_count": len(llm_calls),
                "fallback_count": fallback_count,
            },
        )
