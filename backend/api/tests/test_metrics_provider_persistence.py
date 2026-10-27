#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterator
from uuid import uuid4

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
        MATCH (r:MetricResult) WHERE r.id STARTS WITH 'TEST-res-'
        DETACH DELETE r
        WITH 1 AS _
        MATCH (d:Metric) WHERE d.id STARTS WITH 'TEST-def-'
        DETACH DELETE d
        WITH 1 AS _
        MATCH (s:Session)
        WHERE s.sessionId = $seed_session
           OR s.sessionId STARTS WITH $session_prefix
        DETACH DELETE s
        """,
        {"seed_session": TEST_SESSION_ID, "session_prefix": TEST_SESSION_PREFIX},
    )
    p._db.execute_command(
        """
        MATCH (sp:LLMCall)
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
        MATCH (r:MetricResult {name: $metric_name})-[:measures]->(t)
        WHERE t.sessionId = $resource_id OR t.spanId = $resource_id
        DETACH DELETE r
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
        assert persisted.provider == "Native"
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

    provider._db.execute_command(
        "MERGE (:LLMCall {spanId: $span_id, sessionId: $session_id})",
        {"span_id": span_id, "session_id": session_id},
    )
    try:
        assert provider.save_span_metrics(session_id, span_id, [result]) is True
        rows = provider._db.execute(
            """
            MATCH (t:LLMCall {spanId: $span_id})<-[:measures]-(r:MetricResult)
                  -[:ofMetricType]->(d:Metric {name: $metric_name})
            RETURN d.name AS metric_id, d.metricProvider AS provider
            """,
            {"span_id": span_id, "metric_name": metric_name},
        )
        assert rows
        assert rows[0]["metric_id"] == metric_name
        assert rows[0]["provider"] == "Native"
        # and the provider reads it back by span id
        persisted = _find_metric(
            provider.get_metrics(span_id, session_id=session_id, hops=0), metric_name
        )
        assert persisted.value == 0.91
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
        MERGE (d:Metric {id: 'TEST-def-' + $metric_name})
        SET d.name = $metric_name, d.metricProvider = 'Native'
        MERGE (r:MetricResult {id: 'TEST-res-' + $session_id + $metric_name})
        SET r.name = $metric_name, r.result = 0.0,
            r.reasoning = '0/13 LLM calls failed', r.timestamp = datetime()
        MERGE (r)-[:ofMetricType]->(d)
        MERGE (r)-[:measures]->(s)
        """,
        {"session_id": session_id, "metric_name": metric_name},
    )

    try:
        persisted = _find_metric(provider.get_metrics(session_id), metric_name)
        assert persisted.value == 0.0
        assert persisted.provider == "Native"
        assert persisted.reasoning == "0/13 LLM calls failed"
        assert persisted.metadata["metric_id"] == metric_name
        assert persisted.metadata["source"] == "Native"
    finally:
        _cleanup_metric(provider, session_id, metric_name)
