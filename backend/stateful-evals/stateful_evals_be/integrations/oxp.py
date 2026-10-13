#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXP span record normalization."""

from typing import Any

from stateful_evals_be.models.spans import SpanRecord


def oxp_span_to_otel(span: dict[str, Any]) -> SpanRecord:
    """Map a OXP SpanMetadataItem to the evaluator's existing OTel format."""
    return {
        "SpanId": span.get("span_id", ""),
        "SpanName": span.get("span_name", ""),
        "SpanAttributes": span.get("span_attributes", {}),
        "StatusCode": span.get("status_code", ""),
        "ServiceName": span.get("service_name", ""),
        "Timestamp": span.get("timestamp", ""),
        "ParentSpanId": span.get("parent_span_id", ""),
        "Duration": span.get("duration", 0),
        "TraceId": span.get("trace_id", ""),
        "Links.TraceId": span.get("links_trace_id", []),
        "Links.SpanId": span.get("links_span_id", []),
        "Links.TraceState": span.get("links_trace_state", []),
        "Links.Attributes": span.get("links_attributes", []),
    }
