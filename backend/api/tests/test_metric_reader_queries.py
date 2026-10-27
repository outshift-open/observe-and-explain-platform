"""Mock-only checks that metric readers use the ontology Metric/MetricResult model."""

from __future__ import annotations

import re

import pytest

from oxp.query_builders import kg, ui
from oxp.query_builders.types import Dialect

_FORBIDDEN = (
    "hasMetric",
    ":Span",
    "hasSpan",
    "measuresCall",
    ".metricResult",
    ".metricName",
)


def _queries() -> list[tuple[str, str]]:
    out = [
        (
            "session_rows",
            ui.collect_page_sessions_query(Dialect.NEO4J, application_id="a")[0],
        ),
        (
            "multi",
            ui.collect_page_sessions_with_stateful_eval_query_multi_query(
                Dialect.NEO4J, application_id="a"
            )[0],
        ),
        (
            "stateful",
            ui.collect_page_sessions_with_stateful_eval_query(
                Dialect.NEO4J, application_id="a"
            )[0],
        ),
        (
            "by_name",
            ui.session_metrics_by_name_query(session_ids=["s"], metric_names=["Cost"])[
                0
            ],
        ),
        ("neighbors", kg.neighbors_query(embedding=[0.1], metric_names=["Cost"])[0]),
        (
            "sg_table",
            ui.semantic_groups_table_query(Dialect.NEO4J, application_id="a")[0],
        ),
        (
            "apps_optimized",
            ui.neo4j_applications_with_metrics_optimized_query(metric_names=["Cost"])[
                0
            ],
        ),
        ("sg", ui.semantic_groups_query(Dialect.NEO4J, application_id="a")[0]),
    ]
    return out


@pytest.mark.parametrize("name,query", _queries())
def test_query_uses_ontology_metric_model(name: str, query: str) -> None:
    assert "MetricResult" in query
    assert ":measures" in query
    assert ":ofMetricType" in query
    for bad in _FORBIDDEN:
        assert bad not in query, f"{name}: {bad}"
    assert not re.search(r"\(\s*\w+\s*\)\s*-\s*\[\s*\]\s*-\s*\(\w+:Metric", query)


def test_neighbors_projects_explicit_maps() -> None:
    q = kg.neighbors_query(embedding=[0.1])[0]
    assert "metricName: metric.name" in q
    assert "metricResult: mres.result" in q
    assert "{.*}" not in q
