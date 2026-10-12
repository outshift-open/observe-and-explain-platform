#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the L9 protocols client logic."""

import json

import pytest

from oxp.client.l9_protocols import (
    _get_application_sessions_with_l9_protocols,
    _get_session_l9_protocols,
)
from oxp.core.exceptions import NotFoundError
from oxp.query_builders.types import Dialect


class _StubDB:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, query, params=None):
        return self.rows


CONCORD = {
    "protocol": "concord",
    "enabled": True,
    "activated": True,
    "metrics": json.dumps(
        {
            "compliance": {"completion": {"passed": True, "terminalState": "COMMIT"}},
            "outcome": {"agentScores": [{"agent": "a", "score": 0.9}]},
        }
    ),
    # A section property overrides the metrics blob.
    "outcome": json.dumps(
        {"agentScores": [{"agent": "a", "score": 0.9}, {"agent": "b", "score": 0.7}]}
    ),
}
ACCORD = {"protocol": "L9-ACCORD", "enabled": True, "activated": False}


def test_session_l9_protocols_mapping():
    db = _StubDB([{"found": True, "reports": [CONCORD, ACCORD, {"enabled": True}]}])
    resp = _get_session_l9_protocols(db, Dialect.NEO4J, session_id="s1")

    assert resp.sessionId == "s1"
    assert [p["protocol"] for p in resp.protocols] == ["L9-ACCORD", "L9-CONCORD"]
    concord = resp.protocols[1]
    assert concord["compliance"]["completion"]["terminalState"] == "COMMIT"
    assert len(concord["outcome"]["agentScores"]) == 2
    assert resp.protocols[0]["activated"] is False


def test_session_l9_protocols_unknown_session():
    with pytest.raises(NotFoundError):
        _get_session_l9_protocols(
            _StubDB([{"found": False, "reports": []}]), Dialect.NEO4J, session_id="x"
        )


def test_sessions_with_l9_protocols_summary():
    row = {
        "sessionId": "s1",
        "startTime": 1790938228.5,
        "sessionMetrics": [],
        "failures": [],
        "l9Reports": [CONCORD, ACCORD],
    }
    empty = {**row, "sessionId": "s2", "l9Reports": []}
    resp = _get_application_sessions_with_l9_protocols(
        _StubDB([row, empty]), Dialect.NEO4J, application_id="app"
    )

    s1, s2 = resp.sessions
    assert [(p.protocol, p.enabled, p.activated) for p in s1.l9Protocols] == [
        ("L9-ACCORD", True, False),
        ("L9-CONCORD", True, True),
    ]
    assert s1.concord == {"terminalState": "COMMIT", "worstOffSatisfaction": 0.7}
    assert s2.l9Protocols == [] and s2.concord is None
