#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Read exported trajectories without retrieval, inference, or persistence."""

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from stateful_evals_be.integrations.oxp import oxp_span_to_otel


def _read_export(path: Path) -> tuple[list[Any], dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("The trajectory file is empty.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        if exc.msg != "Extra data":
            raise ValueError(f"Invalid JSON at line {exc.lineno}: {exc.msg}") from exc
        data = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                data.append(json.loads(line))
            except json.JSONDecodeError as line_exc:
                raise ValueError(
                    f"Invalid JSONL record at line {line_number}: {line_exc.msg}"
                ) from line_exc
    if isinstance(data, dict) and "spans" in data:
        if not isinstance(data["spans"], list):
            raise ValueError("The trajectory's 'spans' field must be an array.")
        return data["spans"], data
    if isinstance(data, dict):
        return [data], {}
    if isinstance(data, list):
        return data, {}
    raise ValueError("Expected a trajectory object, span array, or span JSONL.")


def _timestamp(value: Any) -> tuple[str, int]:
    """Normalize ISO timestamps to sortable UTC while retaining nanoseconds."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("A recorded ISO timestamp is required; none will be invented.")
    match = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?"
        r"(Z|[+-]\d{2}:?\d{2})?",
        value.strip(),
    )
    if not match:
        raise ValueError("Expected an ISO timestamp with at most nanosecond precision.")
    seconds, fraction, offset = match.groups()
    dt = datetime.fromisoformat(seconds + (offset or "+00:00").replace("Z", "+00:00"))
    utc = dt.astimezone(timezone.utc)
    fraction = (fraction or "").ljust(9, "0")
    epoch = utc - datetime(1970, 1, 1, tzinfo=timezone.utc)
    ns = (epoch.days * 86400 + epoch.seconds) * 1_000_000_000 + int(fraction)
    return f"{utc:%Y-%m-%dT%H:%M:%S}.{fraction}Z", ns


def _identifier(value: Any, field: str, *, optional: bool = False) -> str:
    if value is None or value == "":
        if optional:
            return ""
        raise ValueError(f"A recorded {field} is required; none will be invented.")
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string.")
    if not value.strip():
        raise ValueError(f"{field} must not be blank.")
    return value


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object.")
    return value


def _normalize_links(span: dict[str, Any]) -> None:
    # Older database exports omit the dot; SDK exports use a list of link objects.
    for suffix in ("TraceId", "SpanId", "TraceState", "Attributes"):
        if f"Links{suffix}" in span:
            span.setdefault(f"Links.{suffix}", span[f"Links{suffix}"])
    if "links" in span:
        links = span["links"]
        if not isinstance(links, list):
            raise ValueError("links must be an array.")
        contexts = []
        attributes = []
        for link in links:
            _mapping(link, "link")
            context = _mapping(link.get("context", link), "link context")
            _identifier(context.get("span_id"), "linked span_id")
            contexts.append(context)
            attributes.append(_mapping(link.get("attributes", {}), "link attributes"))
        for suffix, key in (
            ("TraceId", "trace_id"),
            ("SpanId", "span_id"),
            ("TraceState", "trace_state"),
        ):
            span.setdefault(f"Links.{suffix}", [c.get(key, "") for c in contexts])
        span.setdefault("Links.Attributes", attributes)
    ids = span.get("Links.SpanId", [])
    if not isinstance(ids, list):
        raise ValueError("Links.SpanId must be an array.")
    for value in ids:
        _identifier(value, "linked span_id")
    for suffix, default in (
        ("TraceId", ""),
        ("SpanId", ""),
        ("TraceState", ""),
        ("Attributes", {}),
    ):
        values = span.setdefault(f"Links.{suffix}", [deepcopy(default) for _ in ids])
        if not isinstance(values, list) or len(values) != len(ids):
            raise ValueError("OTel link arrays must have matching lengths.")
    for attributes in span["Links.Attributes"]:
        _mapping(attributes, "link attributes")


def _sdk_span(record: dict[str, Any]) -> dict[str, Any]:
    context = _mapping(record["context"], "context")
    resource = _mapping(record.get("resource", {}), "resource")
    resource_attrs = _mapping(resource.get("attributes", {}), "resource attributes")
    status = _mapping(record.get("status", {}), "status")
    span = deepcopy(record)
    span.update(
        SpanId=context.get("span_id"),
        TraceId=context.get("trace_id", ""),
        ParentSpanId=record.get("parent_id") or "",
        SpanName=record.get("name"),
        SpanAttributes=span["attributes"],
        Timestamp=record.get("start_time"),
        ServiceName=resource_attrs.get("service.name", ""),
        ResourceAttributes=deepcopy(resource_attrs),
        StatusCode=status.get("status_code", ""),
        StatusMessage=status.get("description", ""),
        TraceState=context.get("trace_state", ""),
        SpanKind=record.get("kind", ""),
    )
    if record.get("end_time"):
        span["Duration"] = (
            _timestamp(record["end_time"])[1] - _timestamp(record.get("start_time"))[1]
        )
        if span["Duration"] < 0:
            raise ValueError("Span end_time precedes start_time.")
    return span


def _entity_span(record: dict[str, Any]) -> dict[str, Any]:
    raw = record.get("raw_span_data")
    if raw:
        span = _normalize_span(_mapping(raw, "raw_span_data"))
        if record.get("span_id") and record["span_id"] != span["SpanId"]:
            raise ValueError("Exported span_id disagrees with raw_span_data.SpanId.")
    else:
        span = {
            "SpanId": record.get("span_id"),
            "TraceId": record.get("trace_id", ""),
            "ParentSpanId": record.get("parent_span_id") or "",
            "SpanName": record.get("entity_name"),
            "Timestamp": record.get("timestamp") or record.get("start_time"),
            "ServiceName": record.get("app_name", ""),
            "SpanAttributes": deepcopy(
                record.get("attrs") or record.get("attributes") or {}
            ),
            "StatusCode": "ERROR" if record.get("contains_error") else "UNSET",
        }
        if "links" in record:
            span["links"] = deepcopy(record["links"])
    attrs = _mapping(span["SpanAttributes"], "SpanAttributes")
    if not any(
        attrs.get(f"{prefix}.span.kind") for prefix in ("ioa_observe", "traceloop")
    ):
        attrs["traceloop.span.kind"] = record["entity_type"]
    attrs.setdefault("traceloop.entity.name", record.get("entity_name", ""))
    for direction, flat_prefix in (
        ("input", "gen_ai.prompt."),
        ("output", "gen_ai.completion."),
    ):
        payload = record.get(f"{direction}_payload")
        if payload is None:
            continue
        if any(
            attrs.get(f"{prefix}.entity.{direction}") not in (None, "")
            for prefix in ("ioa_observe", "traceloop")
        ):
            continue
        flat = (
            {k: v for k, v in payload.items() if k.startswith(flat_prefix)}
            if isinstance(payload, dict)
            else {}
        )
        if flat:
            for key, value in flat.items():
                attrs.setdefault(key, deepcopy(value))
        elif not any(key.startswith(flat_prefix) for key in attrs) and not any(
            f"{prefix}.entity.{direction}" in attrs
            for prefix in ("ioa_observe", "traceloop")
        ):
            attrs[f"traceloop.entity.{direction}"] = deepcopy(payload)
    if record.get("tool_definition") is not None:
        attrs.setdefault("tool_definition", deepcopy(record["tool_definition"]))
    for key, target in (
        ("session_id", "session.id"),
        ("agent_id", "agent.id"),
        ("agent_role", "agent.role"),
    ):
        if record.get(key):
            attrs.setdefault(target, record[key])
    return span


def _normalize_span(record: Any) -> dict[str, Any]:
    _mapping(record, "span record")
    if "SpanId" in record and "SpanAttributes" in record:
        span = deepcopy(record)
    elif "context" in record and "attributes" in record and "name" in record:
        span = _sdk_span(record)
    elif "span_id" in record and "span_attributes" in record:
        span = deepcopy(record)
        span.update(oxp_span_to_otel(record))
    elif "span_id" in record and "entity_type" in record:
        span = _entity_span(record)
    else:
        raise ValueError(
            "Unsupported span schema. Expected OTel/Observe spans, database span "
            "records, or exported entity spans; native events.jsonl is not a span export."
        )
    _mapping(span.get("SpanAttributes"), "SpanAttributes")
    span["SpanId"] = _identifier(span.get("SpanId"), "span ID")
    span["TraceId"] = _identifier(span.get("TraceId"), "trace ID", optional=True)
    span["ParentSpanId"] = _identifier(
        span.get("ParentSpanId"), "parent span ID", optional=True
    )
    _identifier(span.get("SpanName"), "span name")
    span["Timestamp"] = _timestamp(span.get("Timestamp"))[0]
    _normalize_links(span)
    return span


def load_trajectory_file(
    path: str | Path, *, session_id: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Return one session ID and normalized spans, with no model calls.

    An explicit session_id relabels a single trajectory; it never combines sessions.
    Envelope metadata (including reward/expected output) is not evaluation input.
    """
    records, envelope = _read_export(Path(path).expanduser())
    if not records:
        raise ValueError("The trajectory contains no spans.")
    spans = []
    recorded_sessions = set()
    trace_sessions: dict[str, set[str]] = {}
    seen_ids: dict[str, str] = {}
    for index, record in enumerate(records, 1):
        try:
            span = _normalize_span(record)
            resource_attrs = _mapping(
                span.get("ResourceAttributes", {}), "ResourceAttributes"
            )
            ids = {
                _identifier(value, "session ID")
                for value in (
                    record.get("session_id"),
                    record.get("sessionId"),
                    span.get("session_id"),
                    span.get("sessionId"),
                    span["SpanAttributes"].get("session.id"),
                    resource_attrs.get("session.id"),
                )
                if value not in (None, "")
            }
            recorded_sessions.update(ids)
            trace_sessions.setdefault(span["TraceId"], set()).update(ids)
            previous_trace = seen_ids.setdefault(span["SpanId"], span["TraceId"])
            if previous_trace != span["TraceId"]:
                raise ValueError("The same span ID occurs in different traces.")
            spans.append(span)
        except ValueError as exc:
            raise ValueError(f"Span record {index}: {exc}") from exc
    if len(recorded_sessions) > 1:
        raise ValueError(
            "The file contains multiple session IDs; export/evaluate each session separately."
        )
    for key in ("session_id", "sessionId"):
        if (
            envelope.get(key)
            and recorded_sessions
            and envelope[key] not in recorded_sessions
        ):
            raise ValueError(
                "The envelope session ID disagrees with its recorded spans."
            )
    declared = (
        envelope.get("session_id") or envelope.get("sessionId") or envelope.get("id")
    )
    if declared:
        declared = _identifier(declared, "trajectory ID")
    traces = {s["TraceId"] for s in spans if s["TraceId"]}
    if (
        len(traces) > 1
        and not declared
        and (not recorded_sessions or any(not trace_sessions[t] for t in traces))
    ):
        raise ValueError(
            "Multiple traces have no shared session identity; export one trajectory per file."
        )
    inferred = next(iter(recorded_sessions), None) or declared
    if not inferred and len(traces) == 1:
        inferred = next(iter(traces))
    selected = session_id if session_id is not None else inferred
    if selected is None:
        raise ValueError(
            "No session or trace ID was recorded; supply session_id explicitly."
        )
    _identifier(selected, "session ID")
    spans.sort(key=lambda s: s["Timestamp"])
    return selected, spans
