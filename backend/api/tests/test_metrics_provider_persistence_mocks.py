#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from oxp.interfaces.models import MetricResult
from oxp.providers import OXPMetricsProvider


class _FakeConnector:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.commands = []

    def ensure_connected(self):
        return None

    def execute(self, query, params):
        return self.rows

    def execute_command(self, query, params):
        self.commands.append((query, params))
        return []


def test_save_metrics_persists_scalar_metric_result_and_explicit_fields() -> None:
    connector = _FakeConnector()
    provider = OXPMetricsProvider(db=connector)

    result = MetricResult(
        metric_id="LLMErrorRate",
        resource_id="session-1",
        provider="Native",
        value=0.0,
        reasoning="0/13 LLM calls failed",
        metadata={"metric_id": "LLMErrorRate", "source": "worker"},
    )

    assert provider.save_metrics([result]) is True
    assert len(connector.commands) == 1

    query, params = connector.commands[0]
    assert params["result"]["result"] == 0.0
    assert params["result"]["reasoning"] == "0/13 LLM calls failed"
    assert params["definition"]["name"] == "LLMErrorRate"
    assert params["definition"]["metricProvider"] == "Native"
    assert params["resource_id"] == "session-1"
    assert ":ofMetricType" in query and ":measures" in query
    assert "hasMetric" not in query


def test_save_metrics_falls_back_to_metric_name_for_metric_id() -> None:
    connector = _FakeConnector()
    provider = OXPMetricsProvider(db=connector)

    result = MetricResult(
        metric_id="Groundedness",
        resource_id="session-1",
        provider="Native",
        value=0.82,
        reasoning="supported by retrieved context",
        metadata={"source": "worker"},
    )

    assert provider.save_metrics([result]) is True

    _, params = connector.commands[0]
    assert params["definition"]["name"] == "Groundedness"
    assert params["result"]["name"] == "Groundedness"


def test_save_span_metrics_falls_back_to_metric_name_for_metric_id() -> None:
    connector = _FakeConnector()
    provider = OXPMetricsProvider(db=connector)

    result = MetricResult(
        metric_id="Relevancy",
        resource_id="span-1",
        provider="Native",
        value=0.91,
        reasoning="response matches user request",
        metadata={"source": "worker"},
    )

    assert provider.save_span_metrics("session-1", "span-1", [result]) is True

    query, params = connector.commands[0]
    assert params["definition"]["name"] == "Relevancy"
    assert params["resource_id"] == "span-1"
    assert params["session_id"] == "session-1"
    assert "spanId: $resource_id" in query


def test_get_metrics_falls_back_to_the_span_query_when_no_session_matches() -> None:
    class _Seq(_FakeConnector):
        def __init__(self):
            super().__init__()
            self.queries = []

        def execute(self, query, params):
            self.queries.append(query)
            if len(self.queries) == 1:
                return []
            return [
                {
                    "metrics": [
                        {"name": "Relevancy", "result": 0.9, "provider": "Native"}
                    ],
                    "subgraph": None,
                }
            ]

    connector = _Seq()
    results = OXPMetricsProvider(db=connector).get_metrics(
        "span-1", session_id="s1", hops=0
    )
    assert [r.value for r in results] == [0.9]
    assert "Session {sessionId" in connector.queries[0]
    assert "spanId: $span_id" in connector.queries[1]


def test_get_metrics_reads_metric_results() -> None:
    rows = [
        {
            "metrics": [
                {
                    "name": "LLMErrorRate",
                    "result": 0.0,
                    "provider": "Native",
                    "reasoning": "0/13 LLM calls failed",
                }
            ],
            "subgraph": None,
        }
    ]
    provider = OXPMetricsProvider(db=_FakeConnector(rows=rows))

    results = provider.get_metrics("session-1")

    assert len(results) == 1
    assert results[0].metric_id == "LLMErrorRate"
    assert results[0].value == 0.0
    assert results[0].provider == "Native"
    assert results[0].reasoning == "0/13 LLM calls failed"
    assert results[0].metadata == {"subgraph": None}


def test_get_metrics_without_a_provider_falls_back_to_oxp() -> None:
    rows = [{"metrics": [{"name": "Groundedness", "result": 0.87}], "subgraph": None}]

    (result,) = OXPMetricsProvider(db=_FakeConnector(rows=rows)).get_metrics(
        "session-1"
    )

    assert (result.metric_id, result.value, result.provider) == (
        "Groundedness",
        0.87,
        "oxp",
    )
