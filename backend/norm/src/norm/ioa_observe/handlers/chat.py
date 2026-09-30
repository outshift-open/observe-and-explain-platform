#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the "*.chat" span name: LLM, LLMCall, initial/final State, Transition."""

from __future__ import annotations

from typing import Any

from oxp_ontology.models.edges import executesLLM, hasLLMCall, usesLLM
from oxp_ontology.models.nodes import LLM, AgentCall, LLMCall

from ..fields import (
    _first_str,
    _hash_id,
    _to_float,
    _to_int,
    get_agent_id,
    get_duration_ms,
    get_end_time,
    get_session_id,
    get_start_time,
    get_success,
)
from ..registry import Registry
from ..trajectory import add_state_pair_transition


def _extract_system_text(system_instructions: Any) -> str:
    """gen_ai.system_instructions may be a plain string or a list of entries
    -- join whatever's there into one string without assuming a specific
    entry shape."""
    if isinstance(system_instructions, str):
        return system_instructions
    if isinstance(system_instructions, (list, tuple)):
        return "\n".join(str(entry) for entry in system_instructions if entry)
    return ""


def _with_system_instructions(input_messages: Any, system_instructions: Any) -> Any:
    """Fold gen_ai.system_instructions into the model's own input content.

    The gen_ai semantic conventions capture the system prompt separately
    from gen_ai.input.messages (it's a distinct, opt-in attribute) -- without
    this, the system prompt silently never reaches the LLMCall's own initial
    State at all, even when the SDK does capture it.
    """
    system_text = _extract_system_text(system_instructions)
    if not system_text:
        return input_messages
    if isinstance(input_messages, list):
        return [system_text, *input_messages]
    if input_messages:
        return f"{system_text}\n\n{input_messages}"
    return system_text


def handle_chat(
    span: dict[str, Any],
    span_attrs: dict[str, Any],
    registry: Registry,
) -> None:
    session_id = get_session_id(span, span_attrs)
    agent_id = get_agent_id(span, span_attrs)
    span_id = str(span.get("SpanId") or "")
    parent_span_id = str(span.get("ParentSpanId") or "")

    provider = str(span_attrs.get("gen_ai.provider.name") or "")
    model = str(span_attrs.get("gen_ai.request.model") or "")
    if not provider and not model:
        return
    llm_id = f"llm-{provider}-{model}"
    llm, _ = registry.add_if_not_exists(
        LLM(
            id=llm_id,
            name=model or llm_id,
            provider=provider,
        )
    )
    registry.add_edge(usesLLM(source_id=agent_id, target_id=llm.id))

    start_time = get_start_time(span, span_attrs)
    end_time = get_end_time(start_time, span)
    duration_ms = get_duration_ms(span)

    call_id = _hash_id("llmcall", provider, model, span_id)
    llm_call = registry.add(
        LLMCall(
            id=call_id,
            name=f"LLM call ({provider}/{model}) {span_id}",
            sessionId=session_id,
            startTime=start_time,
            endTime=end_time,
            duration=duration_ms,
            spanId=span_id,
            parentSpanId=parent_span_id,
            totalTokenCount=_to_int(span_attrs.get("gen_ai.usage.total_tokens")),
            promptTokenCount=_to_int(span_attrs.get("gen_ai.usage.input_tokens")),
            completionTokenCount=_to_int(span_attrs.get("gen_ai.usage.output_tokens")),
            temperature=_to_float(span_attrs.get("gen_ai.request.temperature")),
            finishReason=_first_str(span_attrs.get("gen_ai.response.finish_reasons")),
            responseId=str(span_attrs.get("gen_ai.response.id") or ""),
            cacheReadTokenCount=_to_int(span_attrs.get("gen_ai.usage.cache_read.input_tokens")),
            success=get_success(span, span_attrs),
        )
    )
    registry.add_edge(executesLLM(source_id=llm_call.id, target_id=llm.id))

    owning_agent_span_id = str(span_attrs.get("ioa_observe.agent.span_id") or "")
    if owning_agent_span_id:
        agent_call = registry.find(
            AgentCall,
            lambda a: a.spanId == owning_agent_span_id,
        )
        if agent_call is not None:
            registry.add_edge(
                hasLLMCall(
                    source_id=agent_call.id,
                    target_id=llm_call.id,
                )
            )

    input_messages = span_attrs.get("gen_ai.input.messages") or ""
    input_text = str(
        _with_system_instructions(input_messages, span_attrs.get("gen_ai.system_instructions"))
        or ""
    )
    output_text = str(span_attrs.get("gen_ai.output.messages") or "")
    add_state_pair_transition(
        registry,
        llm_call.id,
        session_id,
        span_id,
        input_text,
        output_text,
    )
