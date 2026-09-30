#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Span field derivation: read straight off each raw span's own SpanAttributes."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any


def attrs(span: dict[str, Any]) -> dict[str, Any]:
    """Return a span's SpanAttributes map, or {} if absent."""
    return span.get("SpanAttributes") or {}


def get_application_id(span: dict[str, Any], span_attrs: dict[str, Any]) -> str:
    return str(span_attrs.get("application_id") or span.get("ServiceName") or "")


def get_session_id(span: dict[str, Any], span_attrs: dict[str, Any]) -> str:
    """Strip the ``<application_id>_`` prefix ioa-observe puts on session.id.

    Strips the exact application_id prefix rather than splitting on the first
    "_", since application_id itself may contain one.
    """
    raw = str(span.get("SessionId") or span_attrs.get("session.id") or "")
    application_id = get_application_id(span, span_attrs)
    prefix = f"{application_id}_"
    if application_id and raw.startswith(prefix):
        return raw[len(prefix) :]
    return raw.split("_")[-1] if "_" in raw else raw


def get_agent_id(span: dict[str, Any], span_attrs: dict[str, Any]) -> str:
    return str(span.get("AgentId") or span_attrs.get("agent_id") or "")


def get_success(span: dict[str, Any], span_attrs: dict[str, Any]) -> bool:
    """Read the span's own ``execution.success`` attribute (string-valued,
    e.g. "true"/"false"), falling back to the OTel ``StatusCode`` column
    when that attribute is absent: only an explicit "Error" status counts
    as a failure -- "Ok"/"Unset"/anything else defaults to success."""
    raw = span_attrs.get("execution.success")
    if raw:
        return str(raw).strip().lower() == "true"
    return str(span.get("StatusCode") or "").strip().lower() != "error"


def _parse_timestamp_ns(value: str) -> int:
    date_part, _, fractional = value.partition(".")
    dt = datetime.strptime(date_part, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    fractional = (fractional + "000000000")[:9]
    return int(dt.timestamp()) * 1_000_000_000 + int(fractional or 0)


def get_start_time(span: dict[str, Any], span_attrs: dict[str, Any]) -> float:
    """Prefer the SDK's own ``ioa_start_time`` capture; fall back to the
    collector-recorded ``Timestamp`` column if it's absent."""
    raw = span_attrs.get("ioa_start_time")
    if raw not in (None, ""):
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
    timestamp = str(span.get("Timestamp") or "")
    if not timestamp:
        return 0.0
    return _parse_timestamp_ns(timestamp) / 1e9


def get_duration_seconds(span: dict[str, Any]) -> float:
    return float(span.get("Duration") or 0) / 1e9


def get_duration_ms(span: dict[str, Any]) -> float:
    return float(span.get("Duration") or 0) / 1e6


def get_end_time(start_time: float, span: dict[str, Any]) -> float:
    return start_time + get_duration_seconds(span)


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _first_str(value: Any) -> str:
    """gen_ai.response.finish_reasons etc. are array attributes; take element 0."""
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    return str(value or "")


def _hash_id(prefix: str, *parts: str) -> str:
    """Deterministic id from natural identity -- same inputs always produce the
    same id, so edges can reference a node before or after it's built."""
    digest = hashlib.sha1("\x1f".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{digest}"
