#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""L9Report / L9ProtocolExecutionReport persistence, against a fake connector."""

from oxp.interfaces.models import MetricResult
from oxp.providers import OXPL9ReportProvider
from oxp.query_builders import l9_graph, metric_graph


class _FakeConnector:
    def __init__(self, session_exists: bool = True):
        self.session_exists = session_exists
        self.reads: list = []
        self.commands: list = []

    def ensure_connected(self):
        return None

    def execute(self, query, params=None):
        self.reads.append((query, params))
        return [{"sessionId": params["session_id"]}] if self.session_exists else []

    def execute_command(self, query, params=None):
        self.commands.append((query, params))


def _metric(name: str, value, **extra) -> MetricResult:
    return MetricResult(
        metric_id=name,
        resource_id="ignored",
        provider="Accord",
        value=value,
        reasoning="why",
        **extra,
    )


def test_l9_report_lists_the_protocols_enabled_and_activated():
    db = _FakeConnector()
    assert (
        OXPL9ReportProvider(db=db).save_l9_report(
            "s1", ["concord", "accord"], ["accord"]
        )
        is True
    )

    ((query, params),) = db.commands
    assert "MERGE (r:L9Report" in query and "-[:reportsOn]->(s)" in query
    props = params["props"]
    assert props["id"] == l9_graph.l9_report_id("s1") and props["sessionId"] == "s1"
    assert props["protocolsEnabled"] == ["accord", "concord"] and props[
        "protocolsActivated"
    ] == ["accord"]
    assert not any(
        "accord" in key.lower() for key in props
    )  # a new protocol adds a value, not a property


def test_nothing_is_written_for_a_session_that_is_not_in_the_graph():
    db = _FakeConnector(session_exists=False)
    provider = OXPL9ReportProvider(db=db)
    assert provider.save_l9_report("ghost", ["accord"], []) is False
    assert (
        provider.save_protocol_execution_report(
            "ghost", "accord", agents_activated=["sre"]
        )
        is False
    )
    assert (
        provider.save_protocol_execution_metrics(
            "ghost", "accord", [_metric("AccordConverged", 1.0)]
        )
        is False
    )
    assert db.commands == []


def test_participation_is_recorded_on_the_protocol_execution_report():
    db = _FakeConnector()
    provider = OXPL9ReportProvider(db=db)
    assert provider.save_protocol_execution_report(
        "s1",
        "accord",
        enabled_evidence="system_prompt",
        skills_enabled=["l9-accord-initiator"],
        skills_activated=["l9-accord-initiator"],
        agents_enabled=["sre", "db"],
        agents_activated=["sre"],
    )
    ((query, params),) = db.commands
    assert (
        "MERGE (p:L9ProtocolExecutionReport" in query and "-[:reportsOn]->(s)" in query
    )
    props = params["props"]
    assert props["id"] == l9_graph.protocol_execution_report_id("s1", "accord")
    assert props["protocol"] == "accord" and props["agentsActivated"] == ["sre"]
    assert props["agentsEnabled"] == ["db", "sre"]
    assert "metricCount" not in props  # the metrics side is not touched


def test_metrics_become_nodes_that_measure_the_report_not_the_session():
    db = _FakeConnector()
    ok = OXPL9ReportProvider(db=db).save_protocol_execution_metrics(
        "s1",
        "accord",
        [_metric("AccordConverged", 1.0), _metric("AccordCacheRate", 0.25)],
    )
    assert ok is True
    report_id = l9_graph.protocol_execution_report_id("s1", "accord")

    upsert, clear, *writes = db.commands
    assert (
        upsert[1]["props"]["metricCount"] == 2
        and "agentsActivated" not in upsert[1]["props"]
    )
    assert "DETACH DELETE r" in clear[0] and clear[1] == {
        "report_id": report_id
    }  # a re-run replaces the results
    assert len(writes) == 2
    for query, params in writes:
        assert "(t:L9ProtocolExecutionReport {id: $resource_id})" in query
        assert ":measures" in query and ":ofMetricType" in query
        assert params["resource_id"] == report_id
        assert params["definition"]["metricProvider"] == "Accord"
    assert {p["result"]["name"] for _, p in writes} == {
        "AccordConverged",
        "AccordCacheRate",
    }


def test_metrics_that_errored_or_have_no_value_are_not_stored():
    db = _FakeConnector()
    metrics = [
        _metric("AccordConverged", 1.0),
        _metric("AccordSkipped", 0.0, error="not applicable"),
    ]
    assert OXPL9ReportProvider(db=db).save_protocol_execution_metrics(
        "s1", "accord", metrics
    )
    upsert, _clear, *writes = db.commands
    assert upsert[1]["props"]["metricCount"] == 1 and len(writes) == 1


def test_the_metric_write_targets_a_report_by_id():
    query, _ = metric_graph.write_metric_result_query(
        "protocol_execution_report", "rid", {"id": "d"}, {"id": "r"}
    )
    assert "MATCH (t:L9ProtocolExecutionReport {id: $resource_id})" in query


def test_a_failing_write_is_reported_not_raised():
    class _Broken(_FakeConnector):
        def execute_command(self, query, params=None):
            raise RuntimeError("neo4j down")

    assert (
        OXPL9ReportProvider(db=_Broken()).save_l9_report("s1", ["accord"], []) is False
    )
