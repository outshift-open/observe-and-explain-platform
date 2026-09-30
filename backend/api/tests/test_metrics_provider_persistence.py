#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
from uuid import uuid4
from collections.abc import Iterator

import pytest
from dotenv import load_dotenv

from oxp.interfaces.models import MetricResult
from oxp.providers import OXPMetricsProvider

load_dotenv()

TEST_SESSION_ID = "TEST-session-metrics-provider-001"
TEST_SESSION_PREFIX = "TEST-session-metrics-provider"
TEST_SPAN_PREFIX = "TEST-span-metrics-provider"


@pytest.fixture(scope="module")
def provider() -> Iterator[OXPMetricsProvider]:
    p = OXPMetricsProvider()
    p._db.execute_command(
        """
        MERGE (s:Session {sessionId: $session_id})
        RETURN s.sessionId AS session_id
        """,
        {"session_id": TEST_SESSION_ID},
    )
    yield p
    p._db.execute_command(
        """
        MATCH (s:Session)
        WHERE s.sessionId = $seed_session
           OR s.sessionId STARTS WITH $session_prefix
        DETACH DELETE s
        """,
        {"seed_session": TEST_SESSION_ID, "session_prefix": TEST_SESSION_PREFIX},
    )
    p._db.execute_command(
        """
        MATCH (sp:Span)
        WHERE sp.spanId STARTS WITH $span_prefix
        DETACH DELETE sp
        """,
        {"span_prefix": TEST_SPAN_PREFIX},
    )
    p._db.close()


def _resource_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _cleanup_metric(
    provider: OXPMetricsProvider, resource_id: str, metric_name: str
) -> None:
    provider._db.execute_command(
        """
        MATCH (m:Metric {resourceId: $resource_id, metricName: $metric_name})
        DETACH DELETE m
        """,
        {"resource_id": resource_id, "metric_name": metric_name},
    )


def _find_metric(results: list[MetricResult], metric_name: str) -> MetricResult:
    for item in results:
        if item.metric_id == metric_name:
            return item
    raise AssertionError(f"Metric {metric_name!r} was not found in provider results")


def test_save_metrics_persists_scalar_metric_result_and_explicit_fields(
    provider: OXPMetricsProvider,
) -> None:
    session_id = TEST_SESSION_ID
    metric_name = "LLMErrorRate"

    result = MetricResult(
        metric_id=metric_name,
        resource_id=session_id,
        provider="Native",
        value=0.0,
        reasoning="0/13 LLM calls failed",
        metadata={"metric_id": metric_name, "source": "worker"},
    )

    try:
        assert provider.save_metrics([result]) is True
        persisted = _find_metric(provider.get_metrics(session_id), metric_name)

        assert persisted.value == 0.0
        assert persisted.reasoning == "0/13 LLM calls failed"
        assert persisted.metadata["metric_id"] == metric_name
        assert persisted.metadata["source"] == "worker"
    finally:
        _cleanup_metric(provider, session_id, metric_name)


def test_save_metrics_falls_back_to_metric_name_for_metric_id(
    provider: OXPMetricsProvider,
) -> None:
    session_id = TEST_SESSION_ID
    metric_name = "Groundedness"

    result = MetricResult(
        metric_id=metric_name,
        resource_id=session_id,
        provider="Native",
        value=0.82,
        reasoning="supported by retrieved context",
        metadata={"source": "worker"},
    )

    try:
        assert provider.save_metrics([result]) is True
        persisted = _find_metric(provider.get_metrics(session_id), metric_name)
        assert persisted.metadata["metric_id"] == metric_name
    finally:
        _cleanup_metric(provider, session_id, metric_name)


def test_save_span_metrics_falls_back_to_metric_name_for_metric_id(
    provider: OXPMetricsProvider,
) -> None:
    session_id = _resource_id("session-metrics-provider")
    span_id = _resource_id("span-metrics-provider")
    metric_name = "Relevancy"

    result = MetricResult(
        metric_id=metric_name,
        resource_id=span_id,
        provider="Native",
        value=0.91,
        reasoning="response matches user request",
        metadata={"source": "worker"},
    )

    try:
        assert provider.save_span_metrics(session_id, span_id, [result]) is True
        # Read span metrics directly from Neo4j because provider.get_metrics only targets sessions.
        rows = provider._db.execute(
            """
            MATCH (span:Span {spanId: $span_id})-[:hasMetric]->(m:Metric {metricName: $metric_name})
            RETURN coalesce(m.metricId, m.metricName) AS metric_id
            """,
            {"span_id": span_id, "metric_name": metric_name},
        )
        assert rows
        assert rows[0]["metric_id"] == metric_name
    finally:
        _cleanup_metric(provider, span_id, metric_name)


def test_get_metrics_reads_new_scalar_metric_result_shape(
    provider: OXPMetricsProvider,
) -> None:
    session_id = _resource_id("session-metrics-provider")
    metric_name = "LLMErrorRate"

    provider._db.execute_command(
        """
        MERGE (s:Session {sessionId: $session_id})
        MERGE (s)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $session_id})
        SET m.metricResult = 0.0,
            m.value = 0.0,
            m.provider = 'Native',
            m.metricId = $metric_name,
            m.source = 'worker',
            m.reasoning = '0/13 LLM calls failed'
        """,
        {"session_id": session_id, "metric_name": metric_name},
    )

    try:
        persisted = _find_metric(provider.get_metrics(session_id), metric_name)
        assert persisted.value == 0.0
        assert persisted.provider == "Native"
        assert persisted.reasoning == "0/13 LLM calls failed"
        assert persisted.metadata["metric_id"] == metric_name
        assert persisted.metadata["source"] == "worker"
    finally:
        _cleanup_metric(provider, session_id, metric_name)


def test_get_metrics_falls_back_to_metric_name_when_metric_id_missing(
    provider: OXPMetricsProvider,
) -> None:
    session_id = _resource_id("session-metrics-provider")
    metric_name = "Groundedness"

    provider._db.execute_command(
        """
        MERGE (s:Session {sessionId: $session_id})
        MERGE (s)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $session_id})
        SET m.metricResult = 0.87,
            m.value = 0.87,
            m.provider = 'Native',
            m.source = 'worker',
            m.reasoning = 'answer is supported by context'
        REMOVE m.metricId
        """,
        {"session_id": session_id, "metric_name": metric_name},
    )

    try:
        persisted = _find_metric(provider.get_metrics(session_id), metric_name)
        assert persisted.metric_id == metric_name
        assert persisted.metadata["metric_id"] == metric_name
    finally:
        _cleanup_metric(provider, session_id, metric_name)


def test_get_metrics_reads_legacy_json_metric_result_shape(
    provider: OXPMetricsProvider,
) -> None:
    session_id = _resource_id("session-metrics-provider")
    metric_name = "WorkflowEfficiency"

    provider._db.execute_command(
        """
        MERGE (s:Session {sessionId: $session_id})
        MERGE (s)-[:hasMetric]->(m:Metric {metricName: $metric_name, resourceId: $session_id})
        SET m.metricResult = $legacy_result,
            m.provider = 'Native'
        """,
        {
            "session_id": session_id,
            "metric_name": metric_name,
            "legacy_result": json.dumps(
                {
                    "value": 1.0,
                    "metric_id": metric_name,
                    "source": "worker",
                    "reasoning": "agent calls form a single chain",
                }
            ),
        },
    )

    try:
        persisted = _find_metric(provider.get_metrics(session_id), metric_name)
        assert persisted.value == 1.0
        assert persisted.reasoning == "agent calls form a single chain"
        assert persisted.metadata["metric_id"] == metric_name
        assert persisted.metadata["source"] == "worker"
    finally:
        _cleanup_metric(provider, session_id, metric_name)
