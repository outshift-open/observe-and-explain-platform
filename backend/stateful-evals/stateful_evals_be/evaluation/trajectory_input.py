#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Turn a normalized trajectory into the step dicts the processor ingests.

A trajectory (see :mod:`stateful_evals_be.models.trajectory`) is a list of
LLM, tool and agent steps with the raw text of their input and output, already
ordered. This module only parses that text and derives the session-level inputs
(policy, root request, roster, final answer); it reads no database.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any

from stateful_evals_be.evaluation.span_normalization import SpanNormalizer
from stateful_evals_be.models.trajectory import Trajectory

# ----------------------------------------------------------------------
# State content parsing
# ----------------------------------------------------------------------

_DECODER = json.JSONDecoder(strict=False)


def parse_json_values(text: str) -> tuple[list[Any], str]:
    """Decode consecutive JSON values from ``text``.

    State content may hold several values back to back (for example the system
    instructions followed by the chat messages) and its strings may contain raw
    newlines, so decoding is non-strict. Returns the decoded values and any
    undecodable remainder.
    """
    values: list[Any] = []
    pos, length = 0, len(text)
    while pos < length:
        while pos < length and text[pos].isspace():
            pos += 1
        if pos >= length:
            break
        try:
            value, pos = _DECODER.raw_decode(text, pos)
        except json.JSONDecodeError:
            return values, text[pos:]
        values.append(value)
    return values, ""


def _is_message_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, dict) and "role" in item for item in value)
    )


def _is_text_parts(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, (str, dict)) and "role" not in item for item in value)
    )


def _text_of_parts(parts: list[Any]) -> str:
    texts = []
    for part in parts:
        if isinstance(part, str):
            texts.append(part)
        elif isinstance(part, dict) and isinstance(part.get("content"), str):
            texts.append(part["content"])
    return "\n".join(t for t in texts if t.strip())


def parse_llm_input(text: str) -> tuple[str, list[dict[str, Any]]]:
    """Split an LLM call's initial State into ``(system_text, chat_messages)``."""
    if not text:
        return "", []
    values, leftover = parse_json_values(text)
    system_text = ""
    messages: list[dict[str, Any]] = []
    for value in values:
        if _is_message_list(value):
            messages.extend(SpanNormalizer._semconv_chat_messages(value))
        elif _is_text_parts(value) and not system_text:
            system_text = _text_of_parts(value)
        elif isinstance(value, str) and not system_text:
            system_text = value
    if not messages and leftover.strip():
        messages = [{"role": "user", "content": leftover.strip()}]
    return system_text.strip(), messages


def parse_llm_output(text: str) -> list[dict[str, Any]]:
    """Chat messages of an LLM call's final State."""
    if not text:
        return []
    values, leftover = parse_json_values(text)
    messages: list[dict[str, Any]] = []
    for value in values:
        if _is_message_list(value):
            messages.extend(SpanNormalizer._semconv_chat_messages(value))
    if not messages:
        raw = leftover.strip() or text.strip()
        messages = [{"role": "assistant", "content": raw}]
    return messages


def parse_payload(text: str) -> Any:
    """Decode a tool/agent State into the payload the evaluator consumes."""
    if not text:
        return None
    values, leftover = parse_json_values(text)
    if len(values) == 1 and not leftover.strip():
        return values[0]
    return {"value": text}


# ----------------------------------------------------------------------
# Step -> evaluator span dict
# ----------------------------------------------------------------------


def _requested_calls(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    calls = []
    for message in messages:
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            calls.append((str(call.get("id") or ""), str(function.get("name") or "")))
    return [(cid, name) for cid, name in calls if cid]


def build_span_dicts(trajectory: Trajectory) -> list[dict[str, Any]]:
    """Convert a trajectory into the normalized step dicts the processor ingests.

    ``span_id`` is the step's own ``call_id`` and ``parent_span_id`` the id of the
    owning agent call. A tool step is matched to the tool-call id its agent's
    preceding LLM turn requested (first requested id, preferring a name match),
    since that id only appears inside the LLM output text.
    """
    pending: dict[str, deque[tuple[str, str]]] = defaultdict(deque)
    span_dicts: list[dict[str, Any]] = []
    for step in trajectory.get("steps") or []:
        attributes: dict[str, Any] = {}
        input_payload: Any = None
        output_payload: Any = None
        tool_definition = None

        if step["kind"] == "llm":
            system_text, in_messages = parse_llm_input(step.get("input_text") or "")
            out_messages = parse_llm_output(step.get("output_text") or "")
            if system_text:
                in_messages = [{"role": "system", "content": system_text}, *in_messages]
            input_payload = {"messages": in_messages} if in_messages else None
            output_payload = {"messages": out_messages} if out_messages else None
            pending[step.get("agent_id") or ""].extend(_requested_calls(out_messages))
        elif step["kind"] == "tool":
            input_payload = parse_payload(step.get("input_text") or "")
            output_payload = parse_payload(step.get("output_text") or "")
            if step.get("description"):
                tool_definition = {
                    "name": step["name"],
                    "description": step["description"],
                }
            call_id = _claim_tool_call_id(
                pending[step.get("agent_id") or ""], step["name"]
            )
            if call_id:
                attributes["gen_ai.tool.call.id"] = call_id
        else:
            input_payload = parse_payload(step.get("input_text") or "")
            output_payload = parse_payload(step.get("output_text") or "")

        span_dicts.append(
            {
                "entity_type": step["kind"],
                "span_id": step["call_id"],
                "transition_id": step["transition_id"],
                "entity_name": step["name"],
                "agent_id": step.get("agent_id") or None,
                "tool_names": [],
                "agent_role": None,
                "app_name": "unknown",
                "input_payload": _as_dict(input_payload),
                "output_payload": _as_dict(output_payload),
                "tool_definition": tool_definition,
                "contains_error": not step.get("success", True),
                "timestamp": float(step.get("start_time") or 0.0),
                "duration_ns": int(float(step.get("duration_ms") or 0.0) * 1_000_000),
                "parent_span_id": step.get("parent_id") or None,
                "trace_id": None,
                "session_id": trajectory["session_id"],
                "attributes": attributes,
                "links": None,
                "raw_span_data": None,
            }
        )
    return span_dicts


def _claim_tool_call_id(queue: deque[tuple[str, str]], tool_name: str) -> str:
    if not queue:
        return ""
    for index, (call_id, requested) in enumerate(queue):
        if requested and (requested == tool_name or tool_name.startswith(requested)):
            del queue[index]
            return call_id
    return queue.popleft()[0]


def _as_dict(payload: Any) -> Any:
    if payload is None or isinstance(payload, dict):
        return payload or None
    return {"value": payload}


# ----------------------------------------------------------------------
# Session-level inputs derived from the trajectory
# ----------------------------------------------------------------------


def find_root_request(span_dicts: list[dict[str, Any]]) -> str:
    """The user's request: first user message of the first LLM step."""
    for span in span_dicts:
        if span["entity_type"] != "llm":
            continue
        for message in (span.get("input_payload") or {}).get("messages", []):
            if message.get("role") == "user" and message.get("content"):
                return str(message["content"]).strip()
        return ""
    return ""


_ROUTING_KEYS = {"next", "next_agent", "goto", "route", "reasoning"}


def _is_routing_decision(text: str) -> bool:
    values, leftover = parse_json_values(text.strip())
    if leftover.strip() or len(values) != 1 or not isinstance(values[0], dict):
        return False
    return bool(values[0]) and set(values[0]) <= _ROUTING_KEYS


def find_final_answer(span_dicts: list[dict[str, Any]]) -> tuple[str, int]:
    """Latest visible assistant reply that is neither a tool request nor routing."""
    for index in range(len(span_dicts) - 1, -1, -1):
        span = span_dicts[index]
        if span["entity_type"] != "llm":
            continue
        for message in reversed((span.get("output_payload") or {}).get("messages", [])):
            if message.get("role") != "assistant" or message.get("tool_calls"):
                continue
            text = str(message.get("content") or "").strip()
            if text and not _is_routing_decision(text):
                return text, index
    return "", -1


def semantic_contracts(
    span_dicts: list[dict[str, Any]],
) -> list[tuple[str, str, int]]:
    """Each agent's distinct system prompt, as ``(agent_id, text, span_index)``."""
    contracts: list[tuple[str, str, int]] = []
    seen: set[tuple[str, str]] = set()
    for index, span in enumerate(span_dicts):
        if span["entity_type"] != "llm":
            continue
        agent = str(span.get("agent_id") or "unknown")
        for message in (span.get("input_payload") or {}).get("messages", []):
            if message.get("role") != "system":
                continue
            text = str(message.get("content") or "").strip()
            if text and (agent, text) not in seen:
                seen.add((agent, text))
                contracts.append((agent, text, index))
    return contracts


def declared_roster(span_dicts: list[dict[str, Any]]) -> list[tuple[str, int]]:
    """Agents that made an LLM or tool call, with the index of their first span."""
    working = {
        str(s["agent_id"])
        for s in span_dicts
        if s["entity_type"] in {"llm", "tool"} and s.get("agent_id")
    }
    first: dict[str, int] = {}
    for index, span in enumerate(span_dicts):
        agent = str(span.get("agent_id") or "")
        if agent in working:
            first.setdefault(agent, index)
    return sorted(first.items(), key=lambda item: item[1])


def root_policy(span_dicts: list[dict[str, Any]]) -> str:
    """System prompt of the first LLM call (the root agent's)."""
    for span in span_dicts:
        if span["entity_type"] != "llm":
            continue
        for message in (span.get("input_payload") or {}).get("messages", []):
            if message.get("role") == "system" and message.get("content"):
                return str(message["content"]).strip()
    return ""


def tool_definitions(trajectory: Trajectory) -> dict[str, Any]:
    """Tool name -> definition, from the tool steps' descriptions."""
    return {
        str(step["name"]): {"name": step["name"], "description": step["description"]}
        for step in trajectory.get("steps") or []
        if step["kind"] == "tool" and step.get("description")
    }
