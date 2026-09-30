#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for norm.ioa_observe.otel_io: loading raw ClickHouse-shaped OTel
span exports and inferring a run id from them.

No intermediate span shape: ``load_otel_export``/``infer_run_id`` and every
``ioa_observe`` handler consume each span dict directly (``SpanId``,
``ParentSpanId``, ``SpanName``, ``SpanAttributes``, ``Timestamp``,
``Duration``, ...) -- see ``norm.ioa_observe.fields``.
"""

from __future__ import annotations

import json

from norm.ioa_observe.fields import attrs
from norm.ioa_observe.otel_io import infer_run_id, load_otel_export


def _clickhouse_row(**overrides):
    row = {
        "Timestamp": "2026-09-04 16:00:41.521212000",
        "TraceId": "8facfdd6089e05928ffb77e2efae896b",
        "SpanId": "a773755ef4601778",
        "ParentSpanId": "f63635e5535d258a",
        "SpanName": "concierge_agent.agent",
        "ServiceName": "noa-trip-planner-mas",
        "Duration": 627627000,
        "StatusCode": "Ok",
        "SpanAttributes": {
            "application_id": "noa-trip-planner-mas",
            "session.id": "noa-trip-planner-mas_9a419e60-fa38-40de-a1c1-65e687a6e5a3",
            "agent_id": "concierge_agent",
        },
    }
    row.update(overrides)
    return row


class TestLoadOtelExport:
    def test_reads_one_span_per_line(self, tmp_path) -> None:
        path = tmp_path / "trace.jsonl"
        path.write_text(
            "\n".join(json.dumps(_clickhouse_row(SpanId=sid)) for sid in ("s1", "s2")) + "\n",
            encoding="utf-8",
        )
        spans = load_otel_export(path)
        assert [s["SpanId"] for s in spans] == ["s1", "s2"]

    def test_skips_blank_lines(self, tmp_path) -> None:
        path = tmp_path / "trace.jsonl"
        path.write_text(json.dumps(_clickhouse_row()) + "\n\n\n", encoding="utf-8")
        assert len(load_otel_export(path)) == 1


class TestInferRunId:
    def test_strips_app_prefix(self) -> None:
        spans = [
            _clickhouse_row(
                SpanAttributes={
                    "application_id": "noa-trip-planner-mas",
                    "session.id": "noa-trip-planner-mas_9a419e60",
                }
            )
        ]
        assert infer_run_id(spans) == "9a419e60"

    def test_bare_session_id_unchanged(self) -> None:
        spans = [_clickhouse_row(SpanAttributes={"session.id": "9a419e60"})]
        assert infer_run_id(spans) == "9a419e60"

    def test_falls_back_to_default_when_absent(self) -> None:
        spans = [_clickhouse_row(SpanAttributes={})]
        assert infer_run_id(spans, default="fallback") == "fallback"

    def test_skips_spans_without_session_id(self) -> None:
        spans = [
            _clickhouse_row(SpanAttributes={}),
            _clickhouse_row(SpanAttributes={"application_id": "app", "session.id": "app_real-id"}),
        ]
        assert infer_run_id(spans) == "real-id"

    def test_reads_straight_off_span_attributes(self) -> None:
        span = _clickhouse_row()
        assert attrs(span)["agent_id"] == "concierge_agent"
