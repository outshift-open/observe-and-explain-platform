#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the sessions-with-cognitive-observability client logic."""

from oxp.client.applications import (
    _get_application_sessions_with_cognitive_observability,
)
from oxp.query_builders.types import Dialect


class _StubDB:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self.rows


def _row():
    return {
        "sessionId": "s1",
        "startTime": 1790938228.5,
        "duration": 10.0,
        "cost": 0.1,
        "agents": ["a"],
        "tokens": 5,
        "sessionMetrics": [
            {"name": "Policy Safety", "result": 0.9, "metric_id": "x"},
            {"name": "task_completion", "result": '{"value": 0.5}'},
            {"name": "Cost", "result": 0.1},
            {"name": "Goal Alignment", "result": None, "value": None},
        ],
        "failures": [
            {
                "name": "Incomplete Synthesis",
                "presenceProbability": 0.6,
                "remediation": ["A"],
                "description": "desc A",
            },
            {
                "name": "Task Delegation Failure",
                "presenceProbability": 0.95,
                "remediation": '["B", "C"]',
            },
            {"name": "No probability", "code": "X"},
        ],
    }


def test_sessions_with_cognitive_observability_mapping():
    db = _StubDB([_row()])
    resp = _get_application_sessions_with_cognitive_observability(
        db, Dialect.NEO4J, application_id="app", session_id="s1"
    )

    assert db.calls[0][1]["application_id"] == "app"
    assert db.calls[0][1]["session_id"] == "s1"
    (session,) = resp.sessions
    assert session.sessionId == "s1"
    assert [
        (m.name, m.value.value, m.value.unit)
        for m in session.cognitiveObservabilityMetrics
    ] == [
        ("Policy Safety", 0.9, "PERCENTAGE"),
        ("Task Completion", 0.5, "PERCENTAGE"),
    ]
    assert [
        (f.name, f.confidence, f.description, f.remediations)
        for f in session.cognitiveFailures
    ] == [
        ("Task Delegation Failure", 0.95, "", ["B", "C"]),
        ("Incomplete Synthesis", 0.6, "desc A", ["A"]),
    ]


def test_sessions_with_cognitive_observability_empty():
    resp = _get_application_sessions_with_cognitive_observability(
        _StubDB([]), Dialect.NEO4J, application_id="app"
    )
    assert resp.sessions == []
