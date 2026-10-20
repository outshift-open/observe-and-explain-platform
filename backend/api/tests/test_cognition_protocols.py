#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the Cognition protocols client logic."""

import pytest

from oxp.client.cognition_protocols import (
    _build_metric,
    _get_application_sessions_with_cognition_protocols,
    _get_session_cognition_protocols,
)
from oxp.core.exceptions import NotFoundError
from oxp.query_builders.types import Dialect


class _StubDB:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query, params=None):
        return self.rows


COGNITION_PROTOCOL_REPORT = {
    "protocolsEnabled": ["accord", "concord"],
    "protocolsActivated": ["accord"],
    "reportedAt": "2026-10-18T18:41:59Z",
}
ACCORD_REPORT = {
    "report": {
        "protocol": "accord",
        "enabledEvidence": "system_prompt",
        "agentsEnabled": ["a", "b"],
        "agentsActivated": ["a"],
        "skillsEnabled": [],
        "reportedAt": "2026-10-18T18:42:23Z",
    },
    "metrics": [
        {
            "name": "AccordConverged",
            "result": 1.0,
            "reasoning": "",
            "provider": "Accord",
        },
        {
            "name": "AccordLockedTerms",
            "result": 4.0,
            "reasoning": '[{"term": "x", "locked": true}]',
        },
        {"name": "AccordLockRecall", "result": 0.0, "reasoning": "threshold 0.72"},
        {"name": "SomethingNew", "result": 3},
        {"result": 1},
    ],
}


def test_session_cognition_protocols_mapping():
    db = _StubDB(
        [
            {
                "found": True,
                "cognitionProtocolReports": [COGNITION_PROTOCOL_REPORT],
                "executionReports": [ACCORD_REPORT],
            }
        ]
    )
    resp = _get_session_cognition_protocols(db, Dialect.NEO4J, session_id="s1")

    assert resp.sessionId == "s1"
    assert [(p["protocol"], p["enabled"], p["activated"]) for p in resp.protocols] == [
        ("L9-ACCORD", True, True),
        ("L9-CONCORD", True, False),
    ]
    accord, concord = resp.protocols
    assert accord["agentsActivated"] == ["a"]
    assert accord["enabledEvidence"] == "system_prompt"
    assert "skillsEnabled" not in accord  # empty lists are left out
    assert "metrics" not in concord  # not activated: no execution report

    by_name = {m["name"]: m for m in accord["metrics"]}
    assert len(by_name) == 4  # the nameless metric is dropped
    assert by_name["AccordConverged"]["section"] == "convergence"
    assert by_name["AccordConverged"]["value"] == 1.0
    assert "reasoning" not in by_name["AccordConverged"]  # empty
    assert by_name["AccordLockedTerms"]["details"] == [{"term": "x", "locked": True}]
    assert by_name["AccordLockRecall"]["value"] == 0.0  # zero is a value, not "no data"
    assert by_name["AccordLockRecall"]["reasoning"] == "threshold 0.72"
    assert by_name["SomethingNew"]["section"] == "other"
    assert (
        _build_metric({"name": "AccordGlossaryUptake", "result": 1.0})["section"]
        == "benefits"
    )
    assert (
        _build_metric({"name": "AccordGlossaryInfluence", "result": 0.5})["section"]
        == "benefits"
    )


def test_session_cognition_protocols_execution_report_without_cognition_protocol_report():
    db = _StubDB(
        [
            {
                "found": True,
                "cognitionProtocolReports": [],
                "executionReports": [ACCORD_REPORT],
            }
        ]
    )
    resp = _get_session_cognition_protocols(db, Dialect.NEO4J, session_id="s1")

    assert [(p["protocol"], p["enabled"], p["activated"]) for p in resp.protocols] == [
        ("L9-ACCORD", True, True)
    ]


def test_session_cognition_protocols_no_reports():
    db = _StubDB(
        [{"found": True, "cognitionProtocolReports": [], "executionReports": []}]
    )
    assert (
        _get_session_cognition_protocols(db, Dialect.NEO4J, session_id="s1").protocols
        == []
    )


def test_session_cognition_protocols_unknown_session():
    with pytest.raises(NotFoundError):
        _get_session_cognition_protocols(
            _StubDB(
                [
                    {
                        "found": False,
                        "cognitionProtocolReports": [],
                        "executionReports": [],
                    }
                ]
            ),
            Dialect.NEO4J,
            session_id="x",
        )


def test_sessions_with_cognition_protocols_status():
    row = {
        "sessionId": "s1",
        "startTime": 1790938228.5,
        "sessionMetrics": [],
        "failures": [],
        "cognitionProtocolReports": [COGNITION_PROTOCOL_REPORT],
    }
    empty = {**row, "sessionId": "s2", "cognitionProtocolReports": []}
    resp = _get_application_sessions_with_cognition_protocols(
        _StubDB([row, empty]), Dialect.NEO4J, application_id="app"
    )

    s1, s2 = resp.sessions
    assert [(p.protocol, p.enabled, p.activated) for p in s1.cognitionProtocols] == [
        ("L9-ACCORD", True, True),
        ("L9-CONCORD", True, False),
    ]
    assert s2.cognitionProtocols == []


def test_build_metric_splits_text_and_json_reasoning():
    fair = _build_metric(
        {
            "name": "ConcordScoreFair",
            "result": 1.0,
            "reasoning": 'FAIR; {"a": {"checked": 3}}',
        }
    )
    assert fair["section"] == "benefits"
    assert fair["reasoning"] == "FAIR"
    assert fair["details"] == {"a": {"checked": 3}}

    only_json = _build_metric(
        {"name": "ConcordRounds", "result": 1, "reasoning": '{"budget": 8}'}
    )
    assert only_json["details"] == {"budget": 8}
    assert "reasoning" not in only_json

    # A ``; `` that is not followed by JSON keeps the text whole.
    text = _build_metric({"name": "X", "result": 1, "reasoning": "a; b"})
    assert text["reasoning"] == "a; b"
    assert "details" not in text
