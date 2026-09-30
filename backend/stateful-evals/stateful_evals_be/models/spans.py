#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dictionary-compatible contracts at the evaluator's input boundary."""

from collections.abc import Mapping
from typing import Any, TypeAlias, TypedDict

# Optional keys reflect existing exports: absent telemetry is not fabricated.
# Functional syntax preserves the dotted OTel link-array field names.
SpanRecord = TypedDict(
    "SpanRecord",
    {
        "SpanId": str,
        "TraceId": str,
        "ParentSpanId": str,
        "SpanName": str,
        "Timestamp": str,
        "Duration": int,
        "StatusCode": str,
        "ServiceName": str,
        "SpanAttributes": dict[str, Any],
        "Links.TraceId": list[str],
        "Links.SpanId": list[str],
        "Links.TraceState": list[str],
        "Links.Attributes": list[dict[str, Any]],
        "links": list[dict[str, Any]],
    },
    total=False,
)

# Existing dictionaries and source-specific extension keys remain accepted.
SpanInput: TypeAlias = SpanRecord | Mapping[str, Any]
