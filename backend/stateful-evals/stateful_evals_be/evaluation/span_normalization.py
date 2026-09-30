#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Stateless normalization of recorded spans; no model or database access."""

import hashlib
import os
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from stateful_evals_be.evaluation.coordination import (
    COORDINATION_CONTEXT_ATTRIBUTE,
    CoordinationContext,
)

logger = logging.getLogger(__name__)

_UNKNOWN_AGENT_VALUES = {"", "unknown", "none", "null"}
# Framework runtime names that some instrumentations record as the agent name.
_FRAMEWORK_AGENT_NAMES = {
    "langgraph",
    "langchain",
    "runnablesequence",
    "runnablecallable",
    "agentexecutor",
    "singlethreadedagentruntime",
}
_CALL_ID_ATTRIBUTES = (
    "mas.call.id",
    "gen_ai.tool.call.id",
    "tool_call_id",
    "tool.call.id",
)


class SpanNormalizer:
    """Convert native payloads into evaluator inputs without changing the source."""

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, str):
                    if item.strip():
                        parts.append(item.strip())
                    continue
                if isinstance(item, dict):
                    for key in ("text", "content", "value"):
                        candidate = item.get(key)
                        if isinstance(candidate, str) and candidate.strip():
                            parts.append(candidate.strip())
                            break
            return " ".join(parts).strip()
        return str(value).strip()

    @staticmethod
    def _infer_message_role(
        message: Dict[str, Any], kwargs: Dict[str, Any], attrs: Dict[str, Any]
    ) -> str:
        role = (
            kwargs.get("role")
            or kwargs.get("type")
            or message.get("role")
            or message.get("type")
            or attrs.get("role")
            or attrs.get("type")
            or ""
        )
        role_text = str(role).strip().lower()
        if role_text in {"human", "user"}:
            return "user"
        if role_text in {"ai", "assistant"}:
            return "assistant"
        if role_text in {"system", "tool"}:
            return role_text

        message_id = str(message.get("id", "")).lower()
        if "humanmessage" in message_id:
            return "user"
        if "aimessage" in message_id:
            return "assistant"
        if "systemmessage" in message_id:
            return "system"
        if "toolmessage" in message_id:
            return "tool"
        return "user"

    @staticmethod
    def _extract_message_entry(message: Any) -> Optional[Dict[str, str]]:
        if isinstance(message, str):
            text = message.strip()
            if text:
                return {"role": "user", "content": text}
            return None
        if not isinstance(message, dict):
            return None

        kwargs = (
            message.get("kwargs", {}) if isinstance(message.get("kwargs"), dict) else {}
        )
        attrs = (
            message.get("attributes", {})
            if isinstance(message.get("attributes"), dict)
            else {}
        )
        role = SpanNormalizer._infer_message_role(message, kwargs, attrs)
        content = SpanNormalizer._normalize_text(
            kwargs.get("content")
            if kwargs.get("content") is not None
            else message.get("content")
        )
        if not content:
            content = SpanNormalizer._normalize_text(attrs.get("content"))
        if not content:
            # OTel GenAI semantic conventions carry text in ``parts``.
            content = SpanNormalizer._normalize_text(message.get("parts"))
        if not content:
            return None
        return {"role": role, "content": content}

    @staticmethod
    def _semconv_messages(value: Any) -> List[Dict[str, Any]]:
        """Parse ``gen_ai.input.messages`` / ``gen_ai.output.messages`` values."""
        parsed = SpanNormalizer._load_json_payload(value)
        if isinstance(parsed, dict) and isinstance(parsed.get("messages"), list):
            parsed = parsed["messages"]
        if not isinstance(parsed, list):
            return []
        return [message for message in parsed if isinstance(message, dict)]

    @staticmethod
    def _semconv_chat_messages(value: Any) -> List[Dict[str, Any]]:
        """Turn OTel GenAI ``parts`` messages into ordinary chat messages.

        Text parts become ``content``; ``tool_call`` parts become OpenAI-style
        ``tool_calls``; ``tool_call_response`` parts become ``role: tool``
        messages carrying the call ``id``.
        """

        def as_text(item: Any) -> str:
            return item if isinstance(item, str) else json.dumps(item, default=str)

        messages: List[Dict[str, Any]] = []
        for raw in SpanNormalizer._semconv_messages(value):
            role = str(raw.get("role") or "user").strip().lower()
            texts: List[str] = []
            calls: List[Dict[str, Any]] = []
            responses: List[Dict[str, Any]] = []
            for part in raw.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                kind = part.get("type")
                if kind == "tool_call":
                    calls.append(
                        {
                            "id": part.get("id") or "",
                            "type": "function",
                            "function": {
                                "name": part.get("name") or "",
                                "arguments": as_text(part.get("arguments") or {}),
                            },
                        }
                    )
                elif kind == "tool_call_response":
                    responses.append(
                        {
                            "role": "tool",
                            "tool_call_id": part.get("id") or "",
                            "content": as_text(part.get("response") or ""),
                        }
                    )
                else:
                    text = SpanNormalizer._normalize_text([part])
                    if text:
                        texts.append(text)
            messages.extend(responses)
            if texts or calls:
                message: Dict[str, Any] = {"role": role, "content": "\n".join(texts)}
                if calls:
                    message["tool_calls"] = calls
                messages.append(message)
        return messages

    @staticmethod
    def is_framework_span(attrs: Dict[str, Any]) -> bool:
        """True for LangGraph's own ``execute_task`` / ``execute_tool`` spans.

        These wrap graph nodes and tool calls that other spans already describe,
        so they feed the trajectory context but are not judged and do not
        receive span metrics. Matching is on the semconv operation name and the
        ``langgraph`` provider, so ``execute_tool`` from other providers is kept.
        """
        operation = str(attrs.get("gen_ai.operation.name") or "").strip().lower()
        provider = str(attrs.get("gen_ai.provider.name") or "").strip().lower()
        return provider == "langgraph" and operation in {"execute_task", "execute_tool"}

    @staticmethod
    def _agent_id_candidate(raw_span: Dict[str, Any]) -> str:
        """Return an explicit agent identity recorded on one span, if any.

        Dedicated MAS attributes are trusted as-is, and ``gen_ai.agent.name``
        is accepted unless it names a framework component. The generic
        ``agent_id`` attribute (and a top-level ``agent_id`` column) is accepted
        only when it names an agent rather than a method path such as
        ``moderator.invoke``.
        """
        attrs = raw_span.get("SpanAttributes", {}) or {}
        for value in (attrs.get("mas.agent.id"), attrs.get("agent.id")):
            text = str(value or "").strip()
            if text and text.casefold() not in _UNKNOWN_AGENT_VALUES:
                return text
        for value, path_like_allowed in (
            (attrs.get("gen_ai.agent.name"), True),
            (attrs.get("agent_id"), False),
            (raw_span.get("agent_id"), False),
        ):
            text = str(value or "").strip()
            if (
                text
                and text.casefold() not in _UNKNOWN_AGENT_VALUES
                and text.casefold() not in _FRAMEWORK_AGENT_NAMES
                and (path_like_allowed or not re.search(r"[.()/\s]", text))
            ):
                return text
        return ""

    @classmethod
    def resolve_agent_id(
        cls,
        raw_span: Dict[str, Any],
        spans_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
        *,
        max_depth: int = 16,
    ) -> str:
        """Resolve the acting agent from the span or its nearest ancestor."""
        candidate = cls._agent_id_candidate(raw_span)
        if candidate or not spans_by_id:
            return candidate
        parent_id = raw_span.get("ParentSpanId")
        seen: set = set()
        depth = 0
        while parent_id and depth < max_depth and str(parent_id) not in seen:
            seen.add(str(parent_id))
            parent = spans_by_id.get(str(parent_id))
            if not parent:
                break
            candidate = cls._agent_id_candidate(parent)
            if candidate:
                return candidate
            parent_id = parent.get("ParentSpanId")
            depth += 1
        return ""

    @staticmethod
    def declared_tool_names(attrs: Dict[str, Any]) -> List[str]:
        """Return tool names bound to an LLM call, across telemetry schemas."""
        names: List[str] = []
        definitions = SpanNormalizer._load_json_payload(
            attrs.get("gen_ai.tool.definitions")
        )
        if isinstance(definitions, dict):
            definitions = definitions.get("tools") or [definitions]
        if isinstance(definitions, list):
            for item in definitions:
                if not isinstance(item, dict):
                    continue
                function = item.get("function")
                name = (
                    function.get("name")
                    if isinstance(function, dict)
                    else item.get("name")
                )
                if name:
                    names.append(str(name))
        pattern = re.compile(r"^llm\.request\.functions\.(\d+)\.name$")
        indexed = sorted(
            (int(match.group(1)), str(value))
            for key, value in attrs.items()
            if (match := pattern.match(str(key))) and value
        )
        names.extend(name for _, name in indexed)
        unique: List[str] = []
        for name in names:
            if name not in unique:
                unique.append(name)
        return unique

    @staticmethod
    def _iter_message_lists(payload: Any):
        stack: List[Any] = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                messages = current.get("messages")
                if isinstance(messages, list):
                    yield messages
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        stack.append(value)

    @staticmethod
    def _find_text_by_keys(payload: Any, keys: List[str]) -> str:
        desired = set(keys)
        stack: List[Any] = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, value in current.items():
                    if key in desired:
                        text = SpanNormalizer._normalize_text(value)
                        if text:
                            return text
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        stack.append(value)
        return ""

    @staticmethod
    def _iter_entity_payloads(attrs: Dict[str, Any]):
        for key in (
            "traceloop.entity.input",
            "traceloop.entity.output",
            "ioa_observe.entity.input",
            "ioa_observe.entity.output",
        ):
            value = attrs.get(key)
            if value in (None, ""):
                continue
            parsed = SpanNormalizer._load_json_payload(value)
            if parsed is not None:
                yield parsed

    @staticmethod
    def _first_span_attribute(attrs: Dict[str, Any], *keys: str) -> Any:
        """Return the first populated attribute across telemetry schemas."""
        for key in keys:
            value = attrs.get(key)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _span_kind(cls, attrs: Dict[str, Any]) -> str:
        return str(
            cls._first_span_attribute(
                attrs,
                "traceloop.span.kind",
                "ioa_observe.span.kind",
            )
            or ""
        ).upper()

    @classmethod
    def _entity_input(cls, attrs: Dict[str, Any]) -> Any:
        return cls._first_span_attribute(
            attrs,
            "traceloop.entity.input",
            "ioa_observe.entity.input",
            "input.value",
        )

    @classmethod
    def _entity_output(cls, attrs: Dict[str, Any]) -> Any:
        return cls._first_span_attribute(
            attrs,
            "traceloop.entity.output",
            "ioa_observe.entity.output",
            "output.value",
        )

    @classmethod
    def _entity_name(cls, attrs: Dict[str, Any]) -> Any:
        return cls._first_span_attribute(
            attrs,
            "traceloop.entity.name",
            "ioa_observe.entity.name",
            "tool.name",
        )

    @staticmethod
    def _find_scalar_text_by_keys(payload: Any, keys: List[str]) -> str:
        desired = set(keys)
        stack: List[Any] = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, value in current.items():
                    if key in desired and not isinstance(value, dict):
                        text = SpanNormalizer._normalize_text(value)
                        if text:
                            return text
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(current, list):
                for value in current:
                    if isinstance(value, (dict, list)):
                        stack.append(value)
        return ""

    @staticmethod
    def extract_user_request_history(
        raw_spans: List[Dict[str, Any]],
    ) -> str:
        entries: List[tuple[int, str]] = []
        seen: set[str] = set()
        root_system_text = ""

        def is_moderator_system(text: str) -> bool:
            lower = text.lower()
            return any(
                marker in lower
                for marker in (
                    "you are a moderator",
                    "you are a coordinator",
                    "coordinating a team",
                    "available agents",
                    "delegate sub-tasks",
                )
            )

        def add_entry(span_index: int, text: str) -> None:
            normalized = SpanNormalizer._normalize_text(text)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            entries.append((span_index, normalized))

        for n, span in enumerate(raw_spans):
            attrs = span.get("SpanAttributes", {}) or {}
            for payload in SpanNormalizer._iter_entity_payloads(attrs):
                payload_is_delegated = False
                for message_list in SpanNormalizer._iter_message_lists(payload):
                    parsed_messages = [
                        parsed
                        for message in message_list
                        if (parsed := SpanNormalizer._extract_message_entry(message))
                    ]
                    system_text = " ".join(
                        message.get("content", "")
                        for message in parsed_messages
                        if message.get("role") == "system"
                    ).strip()
                    if system_text and not root_system_text:
                        root_system_text = system_text
                    delegated = bool(
                        root_system_text
                        and system_text
                        and system_text != root_system_text
                        and not is_moderator_system(system_text)
                    )
                    payload_is_delegated = payload_is_delegated or delegated
                    if delegated:
                        continue
                    for parsed in parsed_messages:
                        if parsed.get("role") == "user":
                            add_entry(n, parsed.get("content", ""))

                if not payload_is_delegated:
                    question = SpanNormalizer._find_scalar_text_by_keys(
                        payload,
                        ["question", "user_question"],
                    )
                    if question:
                        add_entry(n, question)

        if not entries:
            return ""
        if len(entries) == 1:
            return entries[0][1]

        recent = entries[-8:]
        lines = [
            "Conversation user requests from structured telemetry, "
            "most recent first; earlier context follows:"
        ]
        for span_index, text in reversed(recent):
            lines.append(f"[User turn, step {span_index + 1}] {text}")
        return "\n".join(lines)

    @staticmethod
    def _payload_has_meaningful_text(payload: Dict[str, Any]) -> bool:
        if not payload:
            return False
        for value in payload.values():
            text = SpanNormalizer._normalize_text(value)
            if text:
                return True
        messages = payload.get("messages")
        return isinstance(messages, list) and any(
            isinstance(part, dict)
            and bool(
                str(part.get("content") or "").strip()
                or part.get("type") in {"tool_call", "function_call"}
            )
            for message in messages
            if isinstance(message, dict)
            for part in message.get("parts") or []
        )

    @staticmethod
    def _load_json_payload(raw_value: Any) -> Any:
        if raw_value is None:
            return None
        if isinstance(raw_value, (dict, list)):
            return raw_value
        if isinstance(raw_value, str):
            stripped = raw_value.strip()
            if not stripped:
                return None
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                return {"value": raw_value}
        return raw_value

    @staticmethod
    def _extract_parent_llm_payloads(
        raw_span: Dict[str, Any],
        spans_by_id: Optional[Dict[str, Dict[str, Any]]],
    ) -> Dict[str, Dict[str, Any]]:
        if not spans_by_id:
            return {"input_payload": {}, "output_payload": {}}

        parent_span_id = raw_span.get("ParentSpanId")
        if not parent_span_id:
            return {"input_payload": {}, "output_payload": {}}

        parent_span = spans_by_id.get(str(parent_span_id))
        if not parent_span:
            return {"input_payload": {}, "output_payload": {}}

        parent_attrs = parent_span.get("SpanAttributes", {}) or {}
        parent_input = SpanNormalizer._load_json_payload(
            SpanNormalizer._entity_input(parent_attrs)
        )
        parent_output = SpanNormalizer._load_json_payload(
            SpanNormalizer._entity_output(parent_attrs)
        )

        input_payload: Dict[str, Any] = {}
        output_payload: Dict[str, Any] = {}

        prompt_messages: List[Dict[str, str]] = []
        for message_list in SpanNormalizer._iter_message_lists(parent_input):
            for message in message_list:
                parsed = SpanNormalizer._extract_message_entry(message)
                if parsed:
                    prompt_messages.append(parsed)
        if not prompt_messages:
            question = SpanNormalizer._find_text_by_keys(
                parent_input, ["question", "query"]
            )
            if question:
                prompt_messages.append({"role": "user", "content": question})

        for idx, message in enumerate(prompt_messages):
            input_payload[f"gen_ai.prompt.{idx}.role"] = message["role"]
            input_payload[f"gen_ai.prompt.{idx}.content"] = message["content"]

        completion_messages: List[str] = []
        for message_list in SpanNormalizer._iter_message_lists(parent_output):
            for message in message_list:
                parsed = SpanNormalizer._extract_message_entry(message)
                if parsed and parsed["role"] in {"assistant", "ai"}:
                    completion_messages.append(parsed["content"])
        if not completion_messages:
            fallback_text = SpanNormalizer._find_text_by_keys(
                parent_output,
                ["final_answer", "answer", "response", "reasoning", "content"],
            )
            if fallback_text:
                completion_messages.append(fallback_text)

        for idx, content in enumerate(completion_messages):
            output_payload[f"gen_ai.completion.{idx}.role"] = "assistant"
            output_payload[f"gen_ai.completion.{idx}.content"] = content

        return {
            "input_payload": input_payload,
            "output_payload": output_payload,
        }

    @staticmethod
    def entity_type(raw_span: Dict[str, Any]) -> str:
        """Classify a raw span as llm, tool, agent, workflow, coordination or other."""
        span_attrs = raw_span.get("SpanAttributes", {}) or {}
        span_name = raw_span.get("SpanName", "")
        span_kind = SpanNormalizer._span_kind(span_attrs)
        if span_name.endswith(".chat") or span_name.endswith(".llm"):
            return "llm"
        if span_name.endswith(".tool"):
            return "tool"
        if span_name.endswith(".agent"):
            return "agent"
        if span_name.endswith(".workflow"):
            return "workflow"
        by_kind = {
            "LLM": "llm",
            "TOOL": "tool",
            "AGENT": "agent",
            "WORKFLOW": "workflow",
            "COORDINATION": "coordination",
        }
        if span_kind in by_kind:
            return by_kind[span_kind]
        if any(str(key).startswith("gen_ai.prompt.") for key in span_attrs):
            return "llm"
        if span_attrs.get("gen_ai.request.model") or span_attrs.get("gen_ai.system"):
            return "llm"
        if span_attrs.get("tool.name"):
            return "tool"
        return "other"

    @staticmethod
    def normalize_span(
        raw_span: Dict[str, Any],
        spans_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        span_attrs = raw_span.get("SpanAttributes", {}) or {}
        span_name = raw_span.get("SpanName", "")
        entity_type = SpanNormalizer.entity_type(raw_span)

        entity_name = span_name.rsplit(".", 1)[0] if "." in span_name else span_name

        input_payload: Dict[str, Any] = {}
        output_payload: Dict[str, Any] = {}
        tool_definition = None

        if entity_type == "llm":
            for key, val in span_attrs.items():
                if key.startswith("gen_ai.prompt"):
                    input_payload[key] = val
                elif key.startswith("gen_ai.completion"):
                    output_payload[key] = val

            raw_input = SpanNormalizer._entity_input(span_attrs)
            raw_output = SpanNormalizer._entity_output(span_attrs)
            if not SpanNormalizer._payload_has_meaningful_text(input_payload):
                parsed_input = SpanNormalizer._load_json_payload(raw_input)
                if parsed_input is not None:
                    input_payload = (
                        parsed_input
                        if isinstance(parsed_input, dict)
                        else {"value": parsed_input}
                    )
            if not SpanNormalizer._payload_has_meaningful_text(output_payload):
                parsed_output = SpanNormalizer._load_json_payload(raw_output)
                if parsed_output is not None:
                    output_payload = (
                        parsed_output
                        if isinstance(parsed_output, dict)
                        else {"value": parsed_output}
                    )
            if not SpanNormalizer._payload_has_meaningful_text(input_payload):
                semconv_input = SpanNormalizer._semconv_chat_messages(
                    span_attrs.get("gen_ai.input.messages")
                )
                if semconv_input:
                    input_payload = {"messages": semconv_input}
            if not SpanNormalizer._payload_has_meaningful_text(output_payload):
                semconv_output = SpanNormalizer._semconv_chat_messages(
                    span_attrs.get("gen_ai.output.messages")
                )
                if semconv_output:
                    output_payload = {"messages": semconv_output}

            if not SpanNormalizer._payload_has_meaningful_text(
                input_payload
            ) or not SpanNormalizer._payload_has_meaningful_text(output_payload):
                parent_payloads = SpanNormalizer._extract_parent_llm_payloads(
                    raw_span=raw_span,
                    spans_by_id=spans_by_id,
                )
                if (
                    not SpanNormalizer._payload_has_meaningful_text(input_payload)
                    and parent_payloads["input_payload"]
                ):
                    input_payload = parent_payloads["input_payload"]
                if (
                    not SpanNormalizer._payload_has_meaningful_text(output_payload)
                    and parent_payloads["output_payload"]
                ):
                    output_payload = parent_payloads["output_payload"]

            entity_name = span_attrs.get(
                "gen_ai.response.model",
                SpanNormalizer._entity_name(span_attrs) or entity_name,
            )
        elif entity_type == "tool":
            entity_name = SpanNormalizer._entity_name(span_attrs) or entity_name
            raw_input = SpanNormalizer._entity_input(span_attrs)
            raw_output = SpanNormalizer._entity_output(span_attrs)
            if raw_input:
                try:
                    input_payload = (
                        json.loads(raw_input)
                        if isinstance(raw_input, str)
                        else raw_input
                    )
                except json.JSONDecodeError:
                    input_payload = {"value": raw_input}
            if raw_output:
                try:
                    output_payload = (
                        json.loads(raw_output)
                        if isinstance(raw_output, str)
                        else raw_output
                    )
                except json.JSONDecodeError:
                    output_payload = {"value": raw_output}
            raw_tool_def = span_attrs.get("tool_definition")
            if raw_tool_def:
                try:
                    tool_definition = (
                        json.loads(raw_tool_def)
                        if isinstance(raw_tool_def, str)
                        else raw_tool_def
                    )
                except json.JSONDecodeError:
                    tool_definition = None
        elif entity_type in {"agent", "coordination", "workflow", "other"}:
            # ``other`` covers framework task/router nodes whose outputs carry
            # routing decisions (for example a LangGraph conditional edge).
            entity_name = SpanNormalizer._entity_name(span_attrs) or entity_name
            parsed_input = SpanNormalizer._load_json_payload(
                SpanNormalizer._entity_input(span_attrs)
            )
            parsed_output = SpanNormalizer._load_json_payload(
                SpanNormalizer._entity_output(span_attrs)
            )
            if parsed_input is not None:
                input_payload = (
                    parsed_input
                    if isinstance(parsed_input, dict)
                    else {"value": parsed_input}
                )
            if parsed_output is not None:
                output_payload = (
                    parsed_output
                    if isinstance(parsed_output, dict)
                    else {"value": parsed_output}
                )

        status_code = str(raw_span.get("StatusCode", "")).upper()
        contains_error = status_code in {"ERROR", "STATUS_CODE_ERROR"}

        return {
            "entity_type": entity_type,
            "span_id": raw_span.get("SpanId", ""),
            "entity_name": entity_name,
            "agent_id": SpanNormalizer.resolve_agent_id(raw_span, spans_by_id) or None,
            "tool_names": (
                SpanNormalizer.declared_tool_names(span_attrs)
                if entity_type == "llm"
                else []
            ),
            "agent_role": span_attrs.get("mas.agent.role")
            or span_attrs.get("agent.role"),
            "app_name": raw_span.get("ServiceName", "unknown"),
            "input_payload": input_payload or None,
            "output_payload": output_payload or None,
            "tool_definition": tool_definition,
            "contains_error": contains_error,
            "timestamp": str(raw_span.get("Timestamp", "")),
            "parent_span_id": raw_span.get("ParentSpanId"),
            "trace_id": raw_span.get("TraceId"),
            "session_id": span_attrs.get("session.id"),
            "attributes": span_attrs,
            "links": raw_span.get("links"),
            "raw_span_data": raw_span,
        }

    @staticmethod
    def extract_coordination_context(
        raw_spans: List[Dict[str, Any]],
    ) -> CoordinationContext:
        for raw_span in raw_spans:
            attrs = raw_span.get("SpanAttributes", {}) or {}
            payload = attrs.get(COORDINATION_CONTEXT_ATTRIBUTE)
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    continue
            if isinstance(payload, dict):
                return CoordinationContext.from_payload(payload)
        return CoordinationContext()

    @staticmethod
    def extract_system_message(raw_spans: List[Dict[str, Any]]) -> str:
        role_key_re = re.compile(r"^gen_ai\.prompt\.(\d+)\.role$")

        for raw_span in raw_spans:
            attrs = raw_span.get("SpanAttributes", {}) or {}

            for key in (
                "policy",
                "system_message",
                "gen_ai.system_message",
                "environment.policy",
            ):
                val = attrs.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

            for key, val in attrs.items():
                match = role_key_re.match(key)
                if not match or str(val).strip().lower() != "system":
                    continue
                idx = match.group(1)
                content_val = attrs.get(f"gen_ai.prompt.{idx}.content")
                if isinstance(content_val, str) and content_val.strip():
                    return content_val.strip()

            input_payload = SpanNormalizer._load_json_payload(
                SpanNormalizer._entity_input(attrs)
            )
            for message_list in SpanNormalizer._iter_message_lists(input_payload):
                for message in message_list:
                    parsed = SpanNormalizer._extract_message_entry(message)
                    if parsed and parsed["role"] == "system":
                        return parsed["content"]

        return ""

    @staticmethod
    def extract_root_request(raw_spans: List[Dict[str, Any]]) -> str:
        """Return the user's request as recorded on a workflow or agent input."""
        for raw_span in raw_spans:
            attrs = raw_span.get("SpanAttributes", {}) or {}
            span_name = str(raw_span.get("SpanName") or "")
            kind = SpanNormalizer._span_kind(attrs)
            if not (
                span_name.endswith(".workflow")
                or kind == "WORKFLOW"
                or span_name.endswith(".graph")
            ):
                continue
            payload = SpanNormalizer._load_json_payload(
                SpanNormalizer._entity_input(attrs)
            )
            question = SpanNormalizer._find_scalar_text_by_keys(
                payload,
                ["question", "user_question", "query", "user_input"],
            )
            if question:
                return question
        return ""

    @staticmethod
    def _first_llm_message(
        raw_span: Dict[str, Any],
    ) -> Optional[Dict[str, str]]:
        """Return the first prompt message of an LLM span in any schema."""
        attrs = raw_span.get("SpanAttributes", {}) or {}
        flattened: Dict[int, Dict[str, str]] = {}
        for key, value in attrs.items():
            match = re.match(r"^gen_ai\.prompt\.(\d+)\.(role|content)$", str(key))
            if match:
                flattened.setdefault(int(match.group(1)), {})[match.group(2)] = str(
                    value
                )
        if flattened:
            first = flattened[min(flattened)]
            if first.get("content", "").strip():
                return {
                    "role": first.get("role", "user").strip().lower(),
                    "content": first["content"].strip(),
                }
        payload = SpanNormalizer._load_json_payload(SpanNormalizer._entity_input(attrs))
        for message_list in SpanNormalizer._iter_message_lists(payload):
            for message in message_list:
                parsed = SpanNormalizer._extract_message_entry(message)
                if parsed:
                    return parsed
        for message in SpanNormalizer._semconv_messages(
            attrs.get("gen_ai.input.messages")
        ):
            parsed = SpanNormalizer._extract_message_entry(message)
            if parsed:
                return parsed
        return None

    @staticmethod
    def _prompt_roles(raw_span: Dict[str, Any]) -> List[str]:
        """Roles of an LLM span's prompt messages, in order, in any schema."""
        attrs = raw_span.get("SpanAttributes", {}) or {}
        flattened = sorted(
            (int(match.group(1)), str(value).strip().lower())
            for key, value in attrs.items()
            if (match := re.match(r"^gen_ai\.prompt\.(\d+)\.role$", str(key)))
        )
        if flattened:
            return [role for _, role in flattened]
        payload = SpanNormalizer._load_json_payload(SpanNormalizer._entity_input(attrs))
        for message_list in SpanNormalizer._iter_message_lists(payload):
            roles = [
                parsed["role"]
                for message in message_list
                if (parsed := SpanNormalizer._extract_message_entry(message))
            ]
            if roles:
                return roles
        return [
            str(message.get("role") or "").lower()
            for message in SpanNormalizer._semconv_messages(
                attrs.get("gen_ai.input.messages")
            )
        ]

    @staticmethod
    def extract_agent_semantic_contracts(
        raw_spans: List[Dict[str, Any]],
        root_request: str = "",
    ) -> List[Tuple[str, str, int]]:
        """Extract each agent's deduplicated prompt and structured contract.

        A contract is an agent's system prompt, its structured
        ``agent_contract``, or, when a framework sends instructions in a
        non-system message, the stable first message repeated across that
        agent's LLM calls. The repeated header is cut before the user's request
        or a task slot so that per-call content is not treated as design.
        """
        role_key_re = re.compile(r"^gen_ai\.prompt\.(\d+)\.role$")
        contracts: List[Tuple[str, str, int]] = []
        seen: set[Tuple[str, str]] = set()
        spans_by_id = {
            str(span.get("SpanId")): span for span in raw_spans if span.get("SpanId")
        }

        def append_contract(agent_id: str, content: str, span_index: int) -> None:
            normalized = content.strip()
            identity = (agent_id, normalized)
            if not normalized or identity in seen:
                return
            seen.add(identity)
            contracts.append((agent_id, normalized, span_index))

        headers: Dict[str, List[Tuple[int, str]]] = {}
        # (agent, span) pairs whose call has a user message after the header.
        separate_requests: set[Tuple[str, int]] = set()
        for span_index, raw_span in enumerate(raw_spans):
            attrs = raw_span.get("SpanAttributes", {}) or {}
            agent_id = str(
                SpanNormalizer.resolve_agent_id(raw_span, spans_by_id)
                or raw_span.get("ServiceName")
                or "unknown"
            ).strip()

            input_payload = SpanNormalizer._load_json_payload(
                SpanNormalizer._entity_input(attrs)
            )
            if isinstance(input_payload, dict) and isinstance(
                input_payload.get("agent_contract"), dict
            ):
                contract_text = json.dumps(
                    input_payload["agent_contract"],
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                append_contract(
                    agent_id,
                    f"Agent contract: {contract_text}",
                    span_index,
                )

            for message_list in SpanNormalizer._iter_message_lists(input_payload):
                for message in message_list:
                    parsed = SpanNormalizer._extract_message_entry(message)
                    if parsed and parsed["role"] == "system":
                        append_contract(agent_id, parsed["content"], span_index)

            for key, value in attrs.items():
                match = role_key_re.match(key)
                if not match or str(value).strip().lower() != "system":
                    continue
                content = attrs.get(f"gen_ai.prompt.{match.group(1)}.content")
                if not isinstance(content, str) or not content.strip():
                    continue
                append_contract(agent_id, content, span_index)

            if SpanNormalizer.entity_type(raw_span) == "llm":
                first = SpanNormalizer._first_llm_message(raw_span)
                if first and first["role"] != "system":
                    headers.setdefault(agent_id, []).append(
                        (span_index, first["content"])
                    )
                    roles = SpanNormalizer._prompt_roles(raw_span)
                    if "user" in roles[1:]:
                        separate_requests.add((agent_id, span_index))

        normalized_request = " ".join(str(root_request or "").split())
        request_re = (
            re.compile(rf"(?<!\w){re.escape(normalized_request)}(?!\w)")
            if normalized_request
            else None
        )
        for agent_id, items in headers.items():
            if len(items) < 2:
                continue
            texts = [" ".join(text.split()) for _, text in items]
            prefix = os.path.commonprefix(texts)
            cut_at_slot = False
            if request_re is not None:
                # The request's slot follows the instructions; an earlier
                # match is the request's words inside the instructions.
                position = next(
                    (
                        match.start()
                        for match in request_re.finditer(prefix)
                        if match.start() >= 120
                    ),
                    -1,
                )
                if position >= 0:
                    prefix = prefix[:position]
                    cut_at_slot = True
            task_slot = re.search(r"\b(?:Your task|Task|QUERY)\s*:", prefix)
            if task_slot and task_slot.start() >= 120:
                prefix = prefix[: task_slot.start()]
                cut_at_slot = True
            if (
                not cut_at_slot
                and all(text == prefix for text in texts)
                and not all(
                    (agent_id, span_index) in separate_requests
                    for span_index, _ in items
                )
            ):
                # Identical first messages with no slot to cut at and no
                # separate request after them: the repeated text may be the
                # request itself (a ReAct loop re-sending the question).
                continue
            if prefix not in texts:
                # A common prefix may end mid-token where the calls diverge.
                cut = max(prefix.rfind(". "), prefix.rfind(": "), prefix.rfind("\n"))
                prefix = prefix[: cut + 1] if cut > 0 else prefix
            prefix = re.sub(r"(?:\bUser|\bQuestion)\s*:?\s*$", "", prefix).strip()
            if len(prefix) >= 120:
                append_contract(agent_id, prefix, items[0][0])
        return contracts

    @staticmethod
    def extract_tool_definitions(raw_spans: List[Dict[str, Any]]) -> Dict[str, Any]:
        tool_defs: Dict[str, Any] = {}

        for raw_span in raw_spans:
            attrs = raw_span.get("SpanAttributes", {}) or {}
            input_payload = SpanNormalizer._load_json_payload(
                SpanNormalizer._entity_input(attrs)
            )
            if not isinstance(input_payload, dict):
                continue
            definitions = input_payload.get("tools")
            if not isinstance(definitions, list):
                continue
            for definition in definitions:
                if not isinstance(definition, dict):
                    continue
                function = definition.get("function")
                function = function if isinstance(function, dict) else {}
                tool_name = function.get("name") or definition.get("name")
                if tool_name:
                    tool_defs.setdefault(str(tool_name), definition)

        for raw_span in raw_spans:
            span_name = str(raw_span.get("SpanName", ""))
            attrs = raw_span.get("SpanAttributes", {}) or {}
            if (
                not span_name.endswith(".tool")
                and SpanNormalizer._span_kind(attrs) != "TOOL"
            ):
                continue
            tool_name = (
                SpanNormalizer._entity_name(attrs) or span_name.rsplit(".", 1)[0]
            )
            raw_tool_def = attrs.get("tool_definition")
            if not raw_tool_def:
                continue
            try:
                parsed = (
                    json.loads(raw_tool_def)
                    if isinstance(raw_tool_def, str)
                    else raw_tool_def
                )
            except json.JSONDecodeError:
                parsed = raw_tool_def
            tool_defs[str(tool_name)] = parsed
        return tool_defs

    @staticmethod
    def _is_effectively_empty_payload(payload: Any) -> bool:
        if payload is None:
            return True
        if isinstance(payload, str):
            return not payload.strip()
        if isinstance(payload, dict):
            for key, value in payload.items():
                key_text = str(key).lower()
                if key_text.endswith(".role") or key_text in {"role", "type"}:
                    continue
                if not SpanNormalizer._is_effectively_empty_payload(value):
                    return False
            return True
        if isinstance(payload, list):
            for value in payload:
                if not SpanNormalizer._is_effectively_empty_payload(value):
                    return False
            return True
        return not str(payload).strip()

    @staticmethod
    def _agent_span_has_routing_or_answer(raw_span: Dict[str, Any]) -> bool:
        attrs = raw_span.get("SpanAttributes", {}) or {}
        raw_output = SpanNormalizer._entity_output(attrs)
        if not raw_output:
            return False

        try:
            parsed = (
                json.loads(raw_output) if isinstance(raw_output, str) else raw_output
            )
        except (json.JSONDecodeError, TypeError):
            return False

        if not isinstance(parsed, dict):
            return False

        if parsed.get("final_answer"):
            return True
        if parsed.get("next_agent") and parsed.get("reasoning"):
            return True
        return False

    @staticmethod
    def deduplicate_spans(raw_spans: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set = set()
        unique: List[Dict[str, Any]] = []

        for span in raw_spans:
            attrs = span.get("SpanAttributes", {}) or {}
            entity_input = SpanNormalizer._entity_input(attrs) or ""
            entity_output = SpanNormalizer._entity_output(attrs) or ""

            prompt_parts = sorted(
                (k, v) for k, v in attrs.items() if k.startswith("gen_ai.prompt.")
            )
            completion_parts = sorted(
                (k, v) for k, v in attrs.items() if k.startswith("gen_ai.completion.")
            )
            content = (
                str(entity_input) if entity_input else "",
                str(entity_output) if entity_output else "",
                str(prompt_parts) if prompt_parts else "",
                str(completion_parts) if completion_parts else "",
                str(attrs.get("gen_ai.input.messages") or ""),
                str(attrs.get("gen_ai.output.messages") or ""),
            )
            if not any(content):
                # With no captured content only an exact re-export is a
                # duplicate; distinct lifecycle and runtime spans are kept.
                raw = (
                    "no-content",
                    str(span.get("SpanId") or ""),
                    str(span.get("SpanName") or ""),
                    str(span.get("Timestamp") or ""),
                )
            else:
                call_id = next(
                    (
                        str(attrs[key])
                        for key in _CALL_ID_ATTRIBUTES
                        if attrs.get(key) not in (None, "")
                    ),
                    "",
                )
                raw = (
                    SpanNormalizer._span_kind(attrs),
                    SpanNormalizer._entity_name(attrs) or "",
                    call_id,
                    *(
                        hashlib.sha256(
                            part.encode("utf-8", errors="replace")
                        ).hexdigest()
                        for part in content
                    ),
                )
            fingerprint = hashlib.sha256(
                "|".join(raw).encode("utf-8", errors="replace")
            ).hexdigest()

            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(span)

        removed = len(raw_spans) - len(unique)
        if removed:
            logger.info(
                f"Span dedup: removed {removed} content-duplicate spans "
                f"({len(raw_spans)} → {len(unique)})"
            )
        return unique

    @staticmethod
    def extract_tool_outputs(
        raw_spans: List[Dict[str, Any]],
        max_per_tool: int = 6000,
    ) -> str:
        parts: list[str] = []
        for n, span in enumerate(raw_spans):
            attrs = span.get("SpanAttributes", {}) or {}
            span_name = span.get("SpanName", "")
            span_kind = SpanNormalizer._span_kind(attrs)
            is_tool = span_name.endswith(".tool") or span_kind == "TOOL"
            if not is_tool:
                continue

            tool_name = (
                SpanNormalizer._entity_name(attrs) or span_name.rsplit(".", 1)[0]
            )
            raw_output = SpanNormalizer._entity_output(attrs)
            if not raw_output:
                continue

            if isinstance(raw_output, str):
                try:
                    parsed = json.loads(raw_output)
                    text = json.dumps(
                        parsed, indent=None, ensure_ascii=False, default=str
                    )
                except (json.JSONDecodeError, TypeError):
                    text = raw_output
            else:
                text = json.dumps(
                    raw_output, indent=None, ensure_ascii=False, default=str
                )

            parts.append(f"[Step {n + 1}, {tool_name}]\n{text[:max_per_tool]}")

        return "\n\n".join(parts)

    @staticmethod
    def extract_final_answer(
        raw_spans: List[Dict[str, Any]],
    ) -> tuple:
        """Return ``(text, span_index)`` for the answer delivered to the user.

        Precedence, from strongest to weakest evidence:

        1. an explicit ``mas.response.final`` marker;
        2. the latest non-workflow span whose output carries ``final_answer``;
        3. the root agent's latest visible reply that is not a tool call or a
           message addressed to another agent;
        4. a workflow span's ``final_answer`` (mapped to the last span that
           emitted the same text, because a workflow starts before its work);
        5. the longest agent or workflow output;
        6. the longest assistant turn replayed in a prompt history.
        """
        explicit_final_text = ""
        explicit_final_index = -1
        final_key_text = ""
        final_key_index = -1
        workflow_final_text = ""
        best_text = ""
        best_index = -1
        history_text = ""
        history_index = -1
        root_system_text = ""
        root_agent_id = ""
        latest_root_text = ""
        latest_root_index = -1
        spans_by_id = {
            str(span.get("SpanId")): span for span in raw_spans if span.get("SpanId")
        }
        services = {
            str(span.get("ServiceName") or "").strip()
            for span in raw_spans
            if str(span.get("ServiceName") or "").strip()
        }

        def is_moderator_system(text: str) -> bool:
            lower = text.lower()
            return any(
                marker in lower
                for marker in (
                    "you are a moderator",
                    "you are a coordinator",
                    "coordinating a team",
                    "available agents",
                    "delegate sub-tasks",
                )
            )

        def delivered_text(text: str) -> tuple:
            """Return ``(user-facing text, addressed only to another agent)``.

            A typed message, or an envelope of typed messages, is delivered to
            the user only through entries with no target or a user target.
            """
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return text, False
            if isinstance(parsed, dict) and isinstance(parsed.get("messages"), list):
                entries = parsed["messages"]
            elif isinstance(parsed, list):
                entries = parsed
            elif isinstance(parsed, dict):
                entries = [parsed]
            else:
                return text, False
            user_texts: List[str] = []
            agent_targets = False
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                target = str(entry.get("target") or entry.get("recipient") or "")
                message = SpanNormalizer._normalize_text(
                    entry.get("message") or entry.get("content")
                )
                if target and "user" not in target.casefold():
                    agent_targets = True
                elif message:
                    user_texts.append(message)
            if user_texts:
                return "\n\n".join(user_texts), False
            return text, agent_targets

        for n, span in enumerate(raw_spans):
            attrs = span.get("SpanAttributes", {}) or {}
            span_name = span.get("SpanName", "")
            span_kind = SpanNormalizer._span_kind(attrs)

            final_marker = attrs.get("mas.response.final", attrs.get("response.final"))
            is_explicit_final = final_marker is True or str(final_marker).lower() in {
                "1",
                "true",
                "yes",
            }
            if is_explicit_final:
                output_payload = SpanNormalizer._load_json_payload(
                    SpanNormalizer._entity_output(attrs)
                )
                text = SpanNormalizer._find_text_by_keys(
                    output_payload,
                    ["final_answer", "answer", "response", "content", "output"],
                )
                if text:
                    explicit_final_text = text
                    explicit_final_index = n

            is_llm = SpanNormalizer.entity_type(span) == "llm"
            is_workflow = span_name.endswith(".workflow") or span_kind == "WORKFLOW"

            if not is_llm:
                raw_output = SpanNormalizer._entity_output(attrs)
                parsed = None
                if raw_output:
                    try:
                        parsed = (
                            json.loads(raw_output)
                            if isinstance(raw_output, str)
                            else raw_output
                        )
                    except (json.JSONDecodeError, TypeError):
                        parsed = None
                if isinstance(parsed, dict):
                    final_text = SpanNormalizer._normalize_text(
                        parsed.get("final_answer")
                    )
                    if final_text:
                        if is_workflow:
                            workflow_final_text = final_text
                        else:
                            final_key_text = final_text
                            final_key_index = n
                is_agent = span_name.endswith(".agent") or span_kind == "AGENT"
                if (is_agent or is_workflow) and parsed:
                    text = SpanNormalizer._find_text_by_keys(
                        parsed,
                        ["final_answer", "answer", "response", "content"],
                    )
                    if text and len(text) > len(best_text):
                        best_text = text
                        best_index = n
                continue

            raw_input = SpanNormalizer._entity_input(attrs)
            input_payload = SpanNormalizer._load_json_payload(raw_input)
            system_text = ""
            if input_payload is not None:
                for message_list in SpanNormalizer._iter_message_lists(input_payload):
                    parsed_messages = [
                        parsed
                        for message in message_list
                        if (parsed := SpanNormalizer._extract_message_entry(message))
                    ]
                    system_text = " ".join(
                        message.get("content", "")
                        for message in parsed_messages
                        if message.get("role") == "system"
                    ).strip()
                    if system_text:
                        break
            if system_text and not root_system_text:
                root_system_text = system_text
            agent_id = SpanNormalizer.resolve_agent_id(span, spans_by_id)
            if not agent_id and len(services) > 1:
                # One service per agent: the service name is the identity.
                agent_id = str(span.get("ServiceName") or "").strip()
            if agent_id and not root_agent_id and not root_system_text:
                root_agent_id = agent_id

            is_root_llm = bool(
                (
                    system_text
                    and (
                        system_text == root_system_text
                        or is_moderator_system(system_text)
                    )
                )
                or (not system_text and root_agent_id and agent_id == root_agent_id)
            )
            if is_root_llm:
                content, has_tool_calls = SpanNormalizer._llm_reply_text(attrs)
                visible_content = re.sub(
                    r"<\|?channel\|?>\s*(?:thought|analysis)?",
                    "",
                    content,
                    flags=re.IGNORECASE,
                ).strip()
                user_text, to_agent = delivered_text(visible_content)
                if content and visible_content and not has_tool_calls and not to_agent:
                    latest_root_text = (
                        content if user_text == visible_content else user_text
                    )
                    latest_root_index = n

            indexed: dict = {}
            for key, val in attrs.items():
                if not key.startswith("gen_ai.prompt."):
                    continue
                parts_k = key.split(".")
                if len(parts_k) >= 4 and parts_k[2].isdigit():
                    idx = int(parts_k[2])
                    if key.endswith(".role"):
                        indexed.setdefault(idx, {})["role"] = str(val).strip().lower()
                    elif key.endswith(".content"):
                        indexed.setdefault(idx, {})["content"] = str(val)

            for idx in sorted(indexed, reverse=True):
                entry = indexed[idx]
                role = entry.get("role", "")
                content = entry.get("content", "").strip()
                if role in ("assistant", "ai") and content:
                    upper = content.upper()
                    if any(
                        upper.startswith(p) for p in ("REASONING:", "THOUGHT:", "PLAN:")
                    ):
                        continue
                    if len(content) > len(history_text):
                        history_text = content
                        history_index = n
                    break

        def emitting_llm_index(text: str, start: int) -> int:
            """Latest LLM span at or after ``start`` whose reply holds ``text``."""
            normalized = " ".join(text.split())
            for n in range(len(raw_spans) - 1, start - 1, -1):
                if SpanNormalizer.entity_type(raw_spans[n]) != "llm":
                    continue
                attrs = raw_spans[n].get("SpanAttributes", {}) or {}
                reply, _ = SpanNormalizer._llm_reply_text(attrs)
                if normalized and normalized in " ".join(reply.split()):
                    return n
            return -1

        if explicit_final_text:
            return explicit_final_text, explicit_final_index
        # A node's final_answer is current unless the root agent replied again
        # later with different text (a sub-agent or stale state carrying one).
        final_key_current = bool(final_key_text) and (
            final_key_index >= latest_root_index
            or " ".join(final_key_text.split()) in " ".join(latest_root_text.split())
        )
        if final_key_current:
            # A node span starts before the LLM call that produced its answer.
            emitted = emitting_llm_index(final_key_text, final_key_index)
            return final_key_text, emitted if emitted >= 0 else final_key_index
        if latest_root_text:
            return latest_root_text, latest_root_index
        if workflow_final_text:
            normalized = " ".join(workflow_final_text.split())
            for n in range(len(raw_spans) - 1, -1, -1):
                attrs = raw_spans[n].get("SpanAttributes", {}) or {}
                emitted = " ".join(
                    " ".join(
                        SpanNormalizer._string_values(
                            SpanNormalizer._load_json_payload(
                                SpanNormalizer._entity_output(attrs)
                            )
                        )
                    ).split()
                )
                reply, _ = SpanNormalizer._llm_reply_text(attrs)
                if normalized and (
                    normalized in emitted or normalized in " ".join(reply.split())
                ):
                    return workflow_final_text, n
            return workflow_final_text, len(raw_spans) - 1
        if best_text:
            return best_text, best_index
        return history_text, history_index

    @staticmethod
    def _string_values(value: Any) -> List[str]:
        """Every string inside a decoded payload, depth first."""
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            return [
                text
                for item in value.values()
                for text in SpanNormalizer._string_values(item)
            ]
        if isinstance(value, list):
            return [
                text for item in value for text in SpanNormalizer._string_values(item)
            ]
        return []

    @staticmethod
    def _llm_reply_text(attrs: Dict[str, Any]) -> Tuple[str, bool]:
        """Return an LLM span's assistant text and whether it requested tools."""
        output_payload = SpanNormalizer._load_json_payload(
            SpanNormalizer._entity_output(attrs)
        )
        if isinstance(output_payload, dict):
            content = SpanNormalizer._normalize_text(output_payload.get("content"))
            if content or output_payload.get("tool_calls"):
                return content, bool(output_payload.get("tool_calls"))
        completion = [
            (key, value)
            for key, value in attrs.items()
            if str(key).startswith("gen_ai.completion.")
        ]
        if completion:
            text = " ".join(
                str(value).strip()
                for key, value in sorted(completion)
                if str(key).endswith(".content") and str(value).strip()
            )
            has_tools = any(".tool_calls." in str(key) for key, _ in completion)
            return text, has_tools
        messages = SpanNormalizer._semconv_messages(attrs.get("gen_ai.output.messages"))
        texts: List[str] = []
        has_tools = False
        for message in messages:
            for part in message.get("parts") or []:
                if not isinstance(part, dict):
                    continue
                if part.get("type") in {"tool_call", "function_call"}:
                    has_tools = True
                elif part.get("content"):
                    texts.append(str(part.get("content")).strip())
            if message.get("content"):
                texts.append(SpanNormalizer._normalize_text(message.get("content")))
        return " ".join(text for text in texts if text), has_tools
