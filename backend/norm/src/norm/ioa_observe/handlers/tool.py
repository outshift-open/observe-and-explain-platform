#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the "*.tool" span name."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import executesTool, hasToolCall, usesTool
from oxp_ontology.models.nodes import AgentCall, Tool, ToolCall

from ..fields import (
    _hash_id,
    get_agent_id,
    get_duration_ms,
    get_end_time,
    get_session_id,
    get_start_time,
    get_success,
)
from ..registry import Registry
from ..trajectory import add_state_pair_transition


def handle_tool(
    span: dict[str, Any],
    span_attrs: dict[str, Any],
    registry: Registry,
) -> None:
    session_id = get_session_id(span, span_attrs)
    agent_id = get_agent_id(span, span_attrs)
    span_id = str(span.get("SpanId") or "")
    parent_span_id = str(span.get("ParentSpanId") or "")
    entity_name = str(span_attrs.get("ioa_observe.entity.name") or "")
    entity_description = str(span_attrs.get("ioa_observe.entity.description") or "")
    if not entity_name:
        return

    tool, _ = registry.add_if_not_exists(
        Tool(
            id=entity_name,
            name=entity_name,
            description=entity_description,
        )
    )
    registry.add_edge(usesTool(source_id=agent_id, target_id=tool.id))

    start_time = get_start_time(span, span_attrs)
    end_time = get_end_time(start_time, span)
    duration_ms = get_duration_ms(span)

    call_id = _hash_id("toolcall", entity_name, span_id)
    tool_call = registry.add(
        ToolCall(
            id=call_id,
            name=f"Tool call ({entity_name}) {span_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=end_time,
            duration=duration_ms,
            spanId=span_id,
            parentSpanId=parent_span_id,
            success=get_success(span, span_attrs),
        )
    )
    registry.add_edge(executesTool(source_id=tool_call.id, target_id=tool.id))

    owning_agent_span_id = str(span_attrs.get("ioa_observe.agent.span_id") or "")
    if owning_agent_span_id:
        agent_call = registry.find(
            AgentCall,
            lambda a: a.spanId == owning_agent_span_id,
        )
        if agent_call is not None:
            registry.add_edge(
                hasToolCall(
                    source_id=agent_call.id,
                    target_id=tool_call.id,
                )
            )

    # Spec text named gen_ai.input/output.messages here too, but that's the
    # .chat attribute set copy-pasted -- the real OTel gen_ai semantic
    # convention (and this codebase's prior convention) for a tool call is
    # gen_ai.tool.call.arguments/.result.
    input_text = str(
        span_attrs.get("gen_ai.tool.call.arguments")
        or span_attrs.get("ioa_observe.entity.input")
        or ""
    )
    output_text = str(
        span_attrs.get("gen_ai.tool.call.result")
        or span_attrs.get("ioa_observe.entity.output")
        or ""
    )
    add_state_pair_transition(
        registry,
        tool_call.id,
        session_id,
        span_id,
        input_text,
        output_text,
    )
