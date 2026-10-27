#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Cognitive failure reports: the properties, the queries and the writer."""

import pytest

from oxp.client.failures import write_cognitive_failure_reports
from oxp.core.exceptions import DatabaseError
from oxp.query_builders import failure_graph as cg


class _Db:
    def __init__(self, session_exists=True, fail=False):
        self.session_exists = session_exists
        self.fail = fail
        self.calls = []

    def execute(self, query, params=None):
        if self.fail:
            raise RuntimeError("neo4j down")
        self.calls.append((query, params))
        return (
            [{"id": params["props"]["id"], "atCall": False}]
            if self.session_exists
            else []
        )


def _detection(code="IC-2", confidence="medium", reasoning="why", call_id=None):
    return {
        "code": code,
        "confidence": confidence,
        "reasoning": reasoning,
        "call_id": call_id,
    }


def test_properties_are_the_ontology_model():
    props = cg.failure_report_properties(
        "s1", "IC-2", "high", "The plan ignored the change.", "llmcall:1"
    )

    assert set(props) == {
        "id",
        "name",
        "code",
        "confidence",
        "reasoning",
        "reportedAt",
    }
    assert props["code"] == "IC-2" and props["name"] == "IC-2"
    assert props["confidence"] == "high"
    assert props["id"].startswith("failurereport:")


def test_the_id_depends_on_session_failure_and_call():
    def report_id(session, code, call):
        return cg.failure_report_properties(session, code, "low", "why", call)["id"]

    ids = {
        report_id("s1", "IC-2", "c1"),
        report_id("s1", "IC-2", "c2"),
        report_id("s1", "IC-2", None),
        report_id("s1", "CC-3", "c1"),
        report_id("s2", "IC-2", "c1"),
    }
    assert len(ids) == 5
    assert report_id("s1", "IC-2", "c1") == report_id("s1", "IC-2", "c1")


@pytest.mark.parametrize("confidence", ["", "certain", "HIGH", None])
def test_an_unknown_confidence_is_refused(confidence):
    with pytest.raises(ValueError, match="confidence"):
        cg.failure_report_properties("s1", "IC-2", confidence, "why")


@pytest.mark.parametrize(("code", "reasoning"), [("", "why"), ("IC-2", " ")])
def test_a_code_and_a_reasoning_are_required(code, reasoning):
    with pytest.raises(ValueError):
        cg.failure_report_properties("s1", code, "low", reasoning)


def test_the_write_query_links_the_session_and_the_call():
    props = cg.failure_report_properties("s1", "IC-2", "low", "why", "toolcall:2")

    query, params = cg.write_failure_report_query("s1", props, "toolcall:2")

    assert "(r)-[:reportsOn]->(s)" in query and "MERGE (r)-[:atCall]->(c)" in query
    assert "SET r = $props" in query  # a rewrite leaves no stale property
    assert "Span" not in query
    assert params["call_id"] == "toolcall:2" and params["session_id"] == "s1"
    assert "LLMCall" in params["call_labels"] and "Session" not in params["call_labels"]


def test_writing_writes_one_query_per_detection_and_deletes_nothing():
    db = _Db()

    written = write_cognitive_failure_reports(
        db, "s1", [_detection("IC-2", call_id="llmcall:1"), _detection("CC-3")]
    )

    assert written == 2
    assert not any("DELETE" in query for query, _ in db.calls)
    assert [c[1]["props"]["code"] for c in db.calls] == ["IC-2", "CC-3"]
    assert [c[1]["call_id"] for c in db.calls] == ["llmcall:1", None]


def test_no_detection_writes_nothing():
    db = _Db()

    assert write_cognitive_failure_reports(db, "s1", []) == 0
    assert db.calls == []


def test_the_same_failure_in_the_same_place_is_one_report():
    db = _Db()

    written = write_cognitive_failure_reports(
        db,
        "s1",
        [_detection("IC-2", "low", "first"), _detection("IC-2", "high", "second")],
    )

    assert written == 1


def test_an_invalid_detection_leaves_the_earlier_reports_alone():
    db = _Db()

    with pytest.raises(ValueError):
        write_cognitive_failure_reports(
            db, "s1", [_detection("IC-2"), _detection("CC-3", confidence="sure")]
        )

    assert db.calls == []


def test_a_missing_session_writes_nothing():
    db = _Db(session_exists=False)

    assert write_cognitive_failure_reports(db, "ghost", [_detection()]) == 0


def test_database_failures_are_reported():
    with pytest.raises(DatabaseError):
        write_cognitive_failure_reports(_Db(fail=True), "s1", [_detection()])


def test_a_blank_session_id_is_refused():
    with pytest.raises(ValueError):
        write_cognitive_failure_reports(_Db(), " ", [_detection()])
