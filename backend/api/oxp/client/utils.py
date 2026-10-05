#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared utilities for the client layer."""

from __future__ import annotations

import ast
import json
import logging
import re
from datetime import datetime, timezone

from oxp.client.constants import (
    COMPLETION_CONTENT,
    COMPLETION_ROLE,
    COST_PER_TOKEN,
    ENTITY_INPUT,
    ENTITY_OUTPUT,
    ERROR_STATUS,
    EXCEPTION_MESSAGE,
    INPUT_TOKENS_KEY,
    KEY_INPUT_COST,
    KEY_INPUT_TOKENS,
    KEY_OUTPUT_COST,
    KEY_OUTPUT_TOKENS,
    KEY_TOTAL_COST,
    KEY_TOTAL_TOKENS,
    LLM_USAGE_TOTAL_TOKENS,
    OUTPUT_TOKENS_KEY,
    PROMPT_CONTENT,
    PROMPT_ROLE,
    SCOPE_NAME_TRACER,
    TRACELOOP_INPUT,
    TRACELOOP_OUTPUT,
)
from oxp.models.otel_traces import Filters, SpanAttribute

logger = logging.getLogger(__name__)


def parse_time_filters(filters: Filters) -> tuple[str | None, str | None]:
    """Return (start_dt, end_dt) as ``'YYYY-MM-DD HH:MM:SS'`` strings or None."""
    start_dt = end_dt = None
    try:
        if filters.start_time is not None:
            start_dt = datetime.fromtimestamp(
                float(filters.start_time), tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass
    try:
        if filters.end_time is not None:
            end_dt = datetime.fromtimestamp(
                float(filters.end_time), tz=timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        pass
    return start_dt, end_dt


# ---------------------------------------------------------------------------
# Generic helpers (connector-agnostic)
# ---------------------------------------------------------------------------


def safe_int(value: str) -> int:
    """Convert *value* to int, returning 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def timestamp_to_epoch(ts: str) -> float:
    """Convert a ``YYYY-MM-DD HH:MM:SS`` string to a Unix epoch float.

    Sub-second precision (microseconds / nanoseconds) is discarded;
    the value is truncated to whole seconds.
    """
    truncated = ts[:19]  # keep only "YYYY-MM-DD HH:MM:SS"
    try:
        dt = datetime.strptime(truncated, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return dt.timestamp()
    except ValueError:
        return 0.0


def epoch_to_dt_str(epoch: float) -> str:
    """Convert a Unix epoch float to ``YYYY-MM-DD HH:MM:SS`` (UTC)."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# Default time window: 10 years back from "now" when no start is given.
_DEFAULT_WINDOW_SECONDS = 10 * 365 * 24 * 3600  # ~10 years


def parse_epoch_range(start_time: str = "", end_time: str = "") -> tuple[float, float]:
    """Convert optional epoch-string parameters to a (start, end) float pair.

    When *start_time* or *end_time* are empty / non-numeric, sensible
    defaults are used:
    - *end_time* defaults to the current UTC time.
    - *start_time* defaults to 10 years before *end_time*.
    """
    now = datetime.now(tz=timezone.utc).timestamp()

    try:
        end_epoch = float(end_time) if end_time else now
    except (ValueError, TypeError):
        end_epoch = now

    try:
        start_epoch = (
            float(start_time) if start_time else end_epoch - _DEFAULT_WINDOW_SECONDS
        )
    except (ValueError, TypeError):
        start_epoch = end_epoch - _DEFAULT_WINDOW_SECONDS

    logger.debug(
        "parse_epoch_range: start=%s (%s), end=%s (%s)",
        start_epoch,
        epoch_to_dt_str(start_epoch),
        end_epoch,
        epoch_to_dt_str(end_epoch),
    )

    return start_epoch, end_epoch


def remove_quotes(value: str) -> str:
    """Strip surrounding double-quotes from a span-attribute value."""
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def parse_span_attributes(raw: str) -> dict[str, str]:
    """Parse the stored span_attributes string into a dict.

    The column stores a Python-dict-like literal
    (``{'key':'value', …}``) or a JSON string.
    ClickHouse Map columns come back as ``{'k1':'v1','k2':'v2'}``
    which may contain embedded quotes/backslashes that break
    ``ast.literal_eval``.
    """
    if not raw:
        return {}
    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        pass
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    # Fallback: parse ClickHouse map format {'key':'value',...}
    # by extracting key-value pairs with a regex.
    if raw.startswith("{") and raw.endswith("}"):
        result: dict[str, str] = {}
        # Match 'key':'value' pairs — keys never contain single quotes,
        # values may contain escaped quotes.
        for m in re.finditer(r"'([^']*?)'\s*:\s*'((?:[^'\\]|\\.|'')*)'", raw):
            result[m.group(1)] = m.group(2)
        if result:
            return result
    return {}


def parse_events_attributes(raw: str) -> list[dict[str, str]]:
    """Parse the stored events_attributes column into a list of dicts.

    Handles multiple formats:
    - Python list of dicts: ``[{'key': 'val'}, ...]``
    - ClickHouse set-of-maps: ``{'{k1=v1, k2=v2}', '{k3=v3}'}``
    - JSON arrays
    """
    if not raw:
        return []
    # Try standard Python literal / JSON first
    try:
        result = ast.literal_eval(raw)
        if isinstance(result, list):
            return result
    except (ValueError, SyntaxError):
        pass
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return result
    except (json.JSONDecodeError, TypeError):
        pass
    # Handle ClickHouse/CSV set-of-maps format: {'{k1=v1, k2=v2}'}
    return parse_clickhouse_set_of_maps(raw)


# ---------------------------------------------------------------------------
# ClickHouse-specific helpers
# ---------------------------------------------------------------------------


def parse_clickhouse_set_of_maps(raw: str) -> list[dict[str, str]]:
    """Parse ``{'{k=v, k2=v2}', '{k3=v3}'}`` into a list of dicts."""
    results: list[dict[str, str]] = []
    stripped = raw.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return results
    # Remove outer braces
    inner = stripped[1:-1].strip()
    if not inner:
        return results
    # Extract each '{...}' block
    for match in re.finditer(r"'\{([^}]*)\}'", inner):
        kv_str = match.group(1)
        d: dict[str, str] = {}
        # Split on ", " but be careful with values containing commas
        # Use a simple key=value parser
        for part in split_kv_pairs(kv_str):
            if "=" in part:
                k, _, v = part.partition("=")
                d[k.strip()] = v.strip()
        if d:
            results.append(d)
    return results


def split_kv_pairs(s: str) -> list[str]:
    """Split 'k1=v1, k2=v2' respecting that values may not contain '='."""
    parts: list[str] = []
    current = ""
    for segment in s.split(", "):
        if "=" in segment and current:
            parts.append(current)
            current = segment
        elif current:
            current += ", " + segment
        else:
            current = segment
    if current:
        parts.append(current)
    return parts


# ---------------------------------------------------------------------------
# Span-attribute builders
# ---------------------------------------------------------------------------


def build_chat_attributes(attrs: dict[str, str]) -> list[SpanAttribute]:
    """Extract chat-type span attributes (prompts, completions, tokens)."""
    result: list[SpanAttribute] = []

    # Prompt / completion pairs – discover indices from the attrs keys
    key_templates = (PROMPT_ROLE, PROMPT_CONTENT, COMPLETION_ROLE, COMPLETION_CONTENT)
    indices: set[int] = set()
    for attr_key in attrs:
        for tpl in key_templates:
            prefix, _, suffix = tpl.partition("{}")
            if attr_key.startswith(prefix) and attr_key.endswith(suffix):
                middle = (
                    attr_key[len(prefix) : len(attr_key) - len(suffix)]
                    if suffix
                    else attr_key[len(prefix) :]
                )
                try:
                    indices.add(int(middle))
                except (ValueError, TypeError):
                    pass

    for i in sorted(indices):
        for key_tpl in key_templates:
            key = key_tpl.format(i)
            value = attrs.get(key, "")
            if value and value != '""':
                clean = remove_quotes(value)
                result.append(SpanAttribute(key=key, value=clean))

    # Token counts + costs
    input_tokens = attrs.get(INPUT_TOKENS_KEY, "")
    if input_tokens:
        result.append(SpanAttribute(key=KEY_INPUT_TOKENS, value=input_tokens))
        cost = safe_int(input_tokens) * COST_PER_TOKEN
        result.append(SpanAttribute(key=KEY_INPUT_COST, value=f"{cost:f}$"))

    output_tokens = attrs.get(OUTPUT_TOKENS_KEY, "")
    if output_tokens:
        result.append(SpanAttribute(key=KEY_OUTPUT_TOKENS, value=output_tokens))
        cost = safe_int(output_tokens) * COST_PER_TOKEN
        result.append(SpanAttribute(key=KEY_OUTPUT_COST, value=f"{cost:f}$"))

    total_tokens = attrs.get(LLM_USAGE_TOTAL_TOKENS, "")
    if total_tokens:
        result.append(SpanAttribute(key=KEY_TOTAL_TOKENS, value=total_tokens))
        cost = safe_int(total_tokens) * COST_PER_TOKEN
        result.append(SpanAttribute(key=KEY_TOTAL_COST, value=f"{cost:f}$"))

    return result


def build_agent_attributes(attrs: dict[str, str]) -> list[SpanAttribute]:
    """Extract agent-type span attributes (chat input/output)."""
    result: list[SpanAttribute] = []
    for key in (ENTITY_INPUT, ENTITY_OUTPUT):
        value = attrs.get(key, "")
        if value and value != '""':
            clean = remove_quotes(value)
            result.append(SpanAttribute(key=key, value=clean))
    return result


def build_tool_attributes(
    attrs: dict[str, str],
    status_code: str,
    events_attrs: list[dict[str, str]],
    scope_name: str = "",
) -> tuple[list[SpanAttribute], str]:
    """Extract tool-type span attributes and any exception message."""
    result: list[SpanAttribute] = []
    exception = ""

    if scope_name == SCOPE_NAME_TRACER:
        input = ENTITY_INPUT
        output = ENTITY_OUTPUT
    else:
        input = TRACELOOP_INPUT
        output = TRACELOOP_OUTPUT

    for key in (output, input):
        value = attrs.get(key, "")
        if value and value != '""':
            clean = remove_quotes(value)
            result.append(SpanAttribute(key=key, value=clean))

    if status_code == ERROR_STATUS and events_attrs:
        exception = events_attrs[0].get(EXCEPTION_MESSAGE, "")

    return result, exception


def extract_agent_description(desc_rows: list, agent_name: str) -> str:
    """Extract agent description from ``agent_start_event`` query results.

    Each row has ``(events_attributes, span_name)``.  The events_attributes
    column may contain a set-of-maps with ``agent_name`` and ``description``
    keys.  We look for the entry whose ``agent_name`` starts with *agent_name*.
    """
    for row in desc_rows:
        raw_events = str(row[0]) if row[0] else ""
        events = parse_events_attributes(raw_events)
        for evt in events:
            evt_agent = evt.get("agent_name", "")
            # agent_name in events is like "noa-web-surfer.perform_web_search"
            # We match on the first segment (before the dot)
            if evt_agent.split(".")[0] == agent_name and evt.get("description", ""):
                return evt["description"]
    return ""


def parse_tools_from_repr(data: str) -> list[dict[str, str]]:
    """Extract tool names and descriptions from a LangChain ToolNode repr string.

    Parses strings like::

        tools(..., _tools_by_name={
            'tool_name': StructuredTool(name='tool_name', description='...', ...),
            ...
        }, ...)

    Returns a list of ``{"name": ..., "description": ...}`` dicts.
    """
    results: list[dict[str, str]] = []
    for m in re.finditer(
        r"StructuredTool\(name='([^']+)',\s*description='(.*?)',\s*args_schema=",
        data,
    ):
        name = m.group(1)
        description = m.group(2).replace("\\n", "\n").strip()
        results.append({"name": name, "description": description, "isTool": True})
    return results
