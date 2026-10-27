#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Mock tests: the DAL metric readers use the ontology Metric + MetricResult model."""

from __future__ import annotations

from unittest.mock import MagicMock

from oxp.client import dal
from oxp.query_builders import dal as q

FORBIDDEN = ("hasMetric", ":Span", "measuresCall")


def _queries() -> list[str]:
    return [
        q.build_all_metrics_for_session_query()[0],
        q.build_all_mas_metric_pairs_query()[0],
        q.build_analysis_data_for_semantic_group_query("g", "h", "emb")[0],
        q.build_session_data_for_ia_inference_query("s", "Cost", "emb")[0],
        q.build_all_metrics_for_a_group_of_sessions_query(["s"], ["Cost"])[0],
        q.build_all_metrics_for_a_group_of_sessions_query(["s"], None)[0],
        q.build_wr_session_metrics_query("s")[0],
        q._build_wr_sessions_by_setting_with_metrics_query("mas")[0],
    ]


def test_queries_use_metric_result_model() -> None:
    for text in _queries():
        assert "MetricResult" in text
        assert ":measures" in text
        for bad in FORBIDDEN:
            assert bad not in text, (bad, text)
    for text in _queries()[:7]:
        assert ":ofMetricType" in text


def test_semantic_group_cleanup_does_not_delete_metrics() -> None:
    assert "OR r:Metric\n" not in q.build_remove_semantic_groups_query(["a"])[0]
    assert "OR r:Metric\n" not in q.build_cleanup_semantic_groups_query(["a"])[0]


def test_report_links_to_every_definition_by_name() -> None:
    db = MagicMock()
    db.execute.return_value = []
    dal._link_report_to_metric_definitions(db, "AnomalyReport", "r1", "Cost")
    query = db.execute.call_args.args[0]
    assert "(b:Metric)" not in query and "MATCH (b:Metric {name: $to_id_0})" in query
    assert "MERGE (a)-[:aboutMetric]->(b)" in query
    assert "sessionId" not in query


def test_metric_definition_ids_fallback() -> None:
    db = MagicMock()
    db.execute.return_value = [{"id": "metric:1"}, {"id": "metric:2"}]
    assert dal._metric_definition_ids(db, "Cost") == ["metric:1", "metric:2"]
    db.execute.return_value = []
    assert dal._metric_definition_ids(db, "Cost") == ["Cost"]
