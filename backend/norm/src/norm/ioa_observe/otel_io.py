#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load raw ClickHouse-shaped OTel span exports.

No transformation into an intermediate span shape: ``normalize()`` and the
``ioa_observe`` handlers consume these dicts directly (``SpanId``,
``ParentSpanId``, ``SpanName``, ``SpanAttributes``, ``Timestamp``,
``Duration``, ...) via ``ioa_observe.fields.attrs()``/``get_session_id()``/etc.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fields import attrs, get_session_id


def load_otel_export(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSONL ClickHouse OTel trace export as a list of raw span dicts."""
    spans: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                spans.append(json.loads(line))
    return spans


def infer_run_id(spans: list[dict[str, Any]], default: str = "unknown-run") -> str:
    """Return the (stripped) session id spans were recorded under."""
    for span in spans:
        session_id = get_session_id(span, attrs(span))
        if session_id:
            return session_id
    return default
