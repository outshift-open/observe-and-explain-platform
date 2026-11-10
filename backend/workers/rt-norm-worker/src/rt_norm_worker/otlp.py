#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Flatten OTLP/JSON export requests into the records ``norm`` normalizes.

The OTel collector's ``otlphttp`` exporter (``encoding: json``) sends nested
``resourceSpans`` / ``resourceLogs``. ``norm`` reads the flat rows the collector's ClickHouse
exporter writes (and that the input files hold): ``SpanName``, ``SpanAttributes``,
``LogAttributes``, ``ServiceName``, ``Timestamp``, ``Duration``, ... This module does that
conversion, one record per span / log record.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any


def _value(value: dict[str, Any]) -> str:
    """An OTLP ``AnyValue`` as the string the ClickHouse exporter stores."""
    if "stringValue" in value:
        return str(value["stringValue"])
    if "boolValue" in value:
        return "true" if value["boolValue"] else "false"
    if "intValue" in value:
        return str(value["intValue"])
    if "doubleValue" in value:
        return str(value["doubleValue"])
    if "arrayValue" in value:
        items = value["arrayValue"].get("values") or []
        return "[" + ", ".join(_value(item) for item in items) + "]"
    if "kvlistValue" in value:
        return str(_attributes(value["kvlistValue"].get("values")))
    if "bytesValue" in value:
        return str(value["bytesValue"])
    return ""


def _attributes(attributes: list[dict[str, Any]] | None) -> dict[str, str]:
    return {str(a["key"]): _value(a.get("value") or {}) for a in attributes or [] if "key" in a}


def _timestamp(unix_nano: Any) -> str:
    """``YYYY-MM-DD HH:MM:SS.nnnnnnnnn`` (UTC), the format of the ClickHouse ``Timestamp`` column."""
    nanos = int(unix_nano or 0)
    seconds, frac = divmod(nanos, 1_000_000_000)
    return f"{datetime.fromtimestamp(seconds, UTC):%Y-%m-%d %H:%M:%S}.{frac:09d}"


def _enum(value: Any, prefix: str) -> str:
    """``SPAN_KIND_INTERNAL`` -> ``Internal`` (JSON may also carry the enum's number)."""
    if isinstance(value, str) and value.startswith(prefix):
        return value[len(prefix) :].capitalize()
    return str(value or "")


_SPAN_KINDS = {0: "Unspecified", 1: "Internal", 2: "Server", 3: "Client", 4: "Producer", 5: "Consumer"}
_STATUS_CODES = {0: "Unset", 1: "Ok", 2: "Error"}


def _resource(resource_item: dict[str, Any]) -> tuple[dict[str, str], str]:
    resource = _attributes((resource_item.get("resource") or {}).get("attributes"))
    return resource, resource.get("service.name", "")


def spans(request: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """The spans of an OTLP ``ExportTraceServiceRequest`` as flat records."""
    for resource_item in request.get("resourceSpans") or []:
        resource, service = _resource(resource_item)
        for scope_item in resource_item.get("scopeSpans") or []:
            scope = scope_item.get("scope") or {}
            for span in scope_item.get("spans") or []:
                start = int(span.get("startTimeUnixNano") or 0)
                end = int(span.get("endTimeUnixNano") or 0)
                kind = span.get("kind", "")
                status = span.get("status") or {}
                code = status.get("code", "")
                yield {
                    "Timestamp": _timestamp(start),
                    "TraceId": span.get("traceId", ""),
                    "SpanId": span.get("spanId", ""),
                    "ParentSpanId": span.get("parentSpanId", ""),
                    "TraceState": span.get("traceState", ""),
                    "SpanName": span.get("name", ""),
                    "SpanKind": _SPAN_KINDS.get(kind, "") if isinstance(kind, int) else _enum(kind, "SPAN_KIND_"),
                    "ServiceName": service,
                    "ResourceAttributes": resource,
                    "ScopeName": scope.get("name", ""),
                    "ScopeVersion": scope.get("version", ""),
                    "SpanAttributes": _attributes(span.get("attributes")),
                    "Duration": str(max(end - start, 0)),
                    "StatusCode": _STATUS_CODES.get(code, "") if isinstance(code, int) else _enum(code, "STATUS_CODE_"),
                    "StatusMessage": status.get("message", ""),
                }


def logs(request: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """The log records of an OTLP ``ExportLogsServiceRequest`` as flat records."""
    for resource_item in request.get("resourceLogs") or []:
        resource, service = _resource(resource_item)
        for scope_item in resource_item.get("scopeLogs") or []:
            scope = scope_item.get("scope") or {}
            for record in scope_item.get("logRecords") or []:
                time = record.get("timeUnixNano") or record.get("observedTimeUnixNano")
                yield {
                    "Timestamp": _timestamp(time),
                    "TraceId": record.get("traceId", ""),
                    "SpanId": record.get("spanId", ""),
                    "SeverityText": record.get("severityText", ""),
                    "SeverityNumber": record.get("severityNumber", 0),
                    "ServiceName": service,
                    "Body": _value(record.get("body") or {}),
                    "ResourceAttributes": resource,
                    "ScopeName": scope.get("name", ""),
                    "ScopeVersion": scope.get("version", ""),
                    "LogAttributes": _attributes(record.get("attributes")),
                }
