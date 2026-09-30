#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
import json
import re
from mce.core.metric import Metric


def _safe_session(context: dict[str, Any]) -> Any:
    """Return the session object from context if available."""
    return context.get("session")


def _conversation_data(context: dict[str, Any]) -> dict[str, Any]:
    """Return conversation data from context or session."""
    data = context.get("conversation_data")
    if isinstance(data, dict):
        return data
    session = _safe_session(context)
    if session is not None:
        session_data = getattr(session, "conversation_data", None)
        if isinstance(session_data, dict):
            return session_data
    return {}


def _conversation_text(context: dict[str, Any]) -> str:
    """Extract the conversation text from context or session."""
    for key in ["conversation_text", "transcript", "conversation"]:
        value = context.get(key)
        if isinstance(value, str) and value:
            return value
    data = _conversation_data(context)
    if "conversation" in data and isinstance(data["conversation"], str):
        return data["conversation"]
    if "elements" in data:
        elements = data.get("elements")
        if isinstance(elements, (list, dict)):
            return json.dumps(elements, indent=2)
        if isinstance(elements, str):
            return elements
    query, response = _query_response(context)
    if query or response:
        return f"User: {query}\nAssistant: {response}".strip()
    return ""


def _query_response(context: dict[str, Any]) -> tuple[str, str]:
    """Extract the input query and final response from context or session."""
    query = context.get("input_query") or context.get("input_text")
    response = context.get("final_response") or context.get("output_text")
    data = _conversation_data(context)
    if not query and isinstance(data.get("query"), str):
        query = data.get("query")
    if not response and isinstance(data.get("response"), str):
        response = data.get("response")
    session = _safe_session(context)
    if session is not None:
        if not query and isinstance(getattr(session, "input_query", None), str):
            query = getattr(session, "input_query")
        if not response and isinstance(getattr(session, "final_response", None), str):
            response = getattr(session, "final_response")

    llm_spans = context.get("llm_spans") or []
    if not llm_spans and session is not None and hasattr(session, "llm_spans"):
        llm_spans = session.llm_spans or []

    if not query:
        for span in llm_spans:
            query = _span_value(span, "inputContent", "prompt", "input_text")
            if query:
                break

    if not response:
        for span in reversed(llm_spans):
            response = _span_value(span, "outputContent", "completion", "output_text")
            if response:
                break

    return query or "", response or ""


def _llm_binary_score(metric: Metric, prompt: str) -> tuple[float, str]:
    """Get a binary score from an LLM response using the first numeric token."""
    response = metric.call_llm(prompt).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", response)
    score = float(match.group()) if match else 0.0
    score = max(0.0, min(1.0, score))
    return score, response


def _span_dict(span: Any) -> dict[str, Any]:
    """Normalize span to a dictionary for attribute access."""
    if isinstance(span, dict):
        return span
    return getattr(span, "__dict__", {})


def _span_attrs(span: Any) -> dict[str, Any]:
    """Extract raw span attributes with multiple fallback keys."""
    data = _span_dict(span)
    if isinstance(data.get("attrs"), dict):
        return data["attrs"]
    raw_span = data.get("raw_span_data")
    if isinstance(raw_span, dict):
        for key in ["SpanAttributes", "attributes"]:
            attrs = raw_span.get(key)
            if isinstance(attrs, dict):
                return attrs
    return {}


def _span_value(span: Any, *keys: str) -> str | None:
    """Return the first available string value from span data or attributes."""
    data = _span_dict(span)
    attrs = _span_attrs(span)
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
        attr_value = attrs.get(key)
        if isinstance(attr_value, str) and attr_value:
            return attr_value
    return None


def _first_number(context: dict[str, Any], keys: list[str]) -> float:
    for key in keys:
        value = context.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return 0.0


def _find_key_value(data: Any, target_key: str) -> Any:
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for value in data.values():
            result = _find_key_value(value, target_key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _find_key_value(item, target_key)
            if result is not None:
                return result
    return None


def _extract_logprobs(span: Any) -> list[float]:
    span_dict = span if isinstance(span, dict) else getattr(span, "__dict__", {})
    output_payload = span_dict.get("output_payload") or span_dict.get("output")
    if output_payload is None:
        return []

    logprobs_block = _find_key_value(output_payload, "logprobs")
    if not isinstance(logprobs_block, dict):
        return []

    content = logprobs_block.get("content")
    if not isinstance(content, list):
        return []

    logprobs: list[float] = []
    for token_dict in content:
        if isinstance(token_dict, dict) and isinstance(
            token_dict.get("logprob"), (int, float)
        ):
            logprobs.append(float(token_dict["logprob"]))
    return logprobs


def _session_logprobs(context: dict[str, Any]) -> list[float]:
    spans = context.get("llm_spans") or []
    session = context.get("session")
    if not spans and session is not None and hasattr(session, "llm_spans"):
        spans = session.llm_spans or []

    logprobs: list[float] = []
    for span in spans:
        logprobs.extend(_extract_logprobs(span))
    return logprobs
