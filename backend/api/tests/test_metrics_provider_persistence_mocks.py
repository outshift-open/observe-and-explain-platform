#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json

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
    assert params["metric_result"] == 0.0
    assert params["metric_value"] == 0.0
    assert params["reasoning"] == "0/13 LLM calls failed"
    assert params["metric_id"] == "LLMErrorRate"
    assert params["source"] == "worker"
    assert "m.value" in query
    assert "m.reasoning" in query


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
    assert params["metric_id"] == "Groundedness"


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

    _, params = connector.commands[0]
    assert params["metric_id"] == "Relevancy"


def test_get_metrics_reads_new_scalar_metric_result_shape() -> None:
    rows = [
        {
            "metrics": [
                {
                    "name": "LLMErrorRate",
                    "result": 0.0,
                    "value": 0.0,
                    "provider": "Native",
                    "metric_id": "LLMErrorRate",
                    "source": "worker",
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
    assert results[0].metadata["metric_id"] == "LLMErrorRate"
    assert results[0].metadata["source"] == "worker"


def test_get_metrics_falls_back_to_metric_name_when_metric_id_missing() -> None:
    rows = [
        {
            "metrics": [
                {
                    "name": "Groundedness",
                    "result": 0.87,
                    "value": 0.87,
                    "provider": "Native",
                    "source": "worker",
                    "reasoning": "answer is supported by context",
                }
            ],
            "subgraph": None,
        }
    ]
    provider = OXPMetricsProvider(db=_FakeConnector(rows=rows))

    results = provider.get_metrics("session-1")

    assert len(results) == 1
    assert results[0].metric_id == "Groundedness"
    assert results[0].metadata["metric_id"] == "Groundedness"


def test_get_metrics_reads_legacy_json_metric_result_shape() -> None:
    rows = [
        {
            "metrics": [
                {
                    "name": "WorkflowEfficiency",
                    "result": json.dumps(
                        {
                            "value": 1.0,
                            "metric_id": "WorkflowEfficiency",
                            "source": "worker",
                            "reasoning": "agent calls form a single chain",
                        }
                    ),
                    "provider": "Native",
                }
            ],
            "subgraph": None,
        }
    ]
    provider = OXPMetricsProvider(db=_FakeConnector(rows=rows))

    results = provider.get_metrics("session-1")

    assert len(results) == 1
    assert results[0].metric_id == "WorkflowEfficiency"
    assert results[0].value == 1.0
    assert results[0].reasoning == "agent calls form a single chain"
    assert results[0].metadata["metric_id"] == "WorkflowEfficiency"
    assert results[0].metadata["source"] == "worker"
