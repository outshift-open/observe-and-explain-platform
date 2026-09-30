#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints import live_topology as live_topology_endpoint
from oxp.client._live_topology import LiveTopologyClient
from oxp.models.live_topology import (
    LiveAgents,
    LiveTools,
    LiveTopologySessions,
    RealtimeTopologyEdge,
    RealtimeTopologyNode,
    RealtimeTopologyResponse,
)
from oxp.query_builders.types import Dialect


class LiveTopologyStubClient:
    def __init__(self) -> None:
        self.requested_session_id: str | None = None

    def get_live_topology_sessions(
        self, *, application_name: str | None = None
    ) -> LiveTopologySessions:
        return LiveTopologySessions(
            sessions=[
                LiveTopologySessions.Session(
                    session_id="session-1",
                    start_time="2026-07-13T10:00:00Z",
                    end_time=None,
                    status="active",
                )
            ]
        )

    def get_live_agents(self) -> LiveAgents:
        return LiveAgents(
            agents=[
                LiveAgents.Agent(
                    agent_name="planner",
                    start_time="2026-07-13T10:01:00Z",
                    end_time="2026-07-13T10:02:00Z",
                    status="completed",
                )
            ]
        )

    def get_live_tools(self) -> LiveTools:
        return LiveTools(
            tools=[
                LiveTools.Tool(
                    tool_name="search_docs",
                    start_time="2026-07-13T10:01:30Z",
                    end_time=None,
                    status="active",
                )
            ]
        )

    def get_realtime_topology(self, *, session_id: str) -> RealtimeTopologyResponse:
        self.requested_session_id = session_id
        return RealtimeTopologyResponse(
            session_id=session_id,
            session_status="active",
            last_updated="2026-07-13T10:03:00Z",
            nodes=[
                RealtimeTopologyNode(
                    id="planner",
                    name="planner",
                    type="agent",
                    status="active",
                    start_time="2026-07-13T10:01:00Z",
                    data={"tools": ["search_docs"]},
                ),
                RealtimeTopologyNode(
                    id="search_docs",
                    name="search_docs",
                    type="tool",
                    status="completed",
                    start_time="2026-07-13T10:01:30Z",
                    end_time="2026-07-13T10:01:45Z",
                ),
            ],
            edges=[
                RealtimeTopologyEdge(
                    source="planner",
                    target="search_docs",
                    label="invokes",
                )
            ],
        )


def test_get_live_topology_sessions() -> None:
    stub = LiveTopologyStubClient()
    app.dependency_overrides[live_topology_endpoint._client] = lambda: stub

    try:
        client = TestClient(app)
        response = client.get("/api/v1/live_topology/test-app/sessions")
    finally:
        app.dependency_overrides.pop(live_topology_endpoint._client, None)

    assert response.status_code == 200
    assert response.json() == {
        "sessions": [
            {
                "session_id": "session-1",
                "start_time": "2026-07-13T10:00:00Z",
                "end_time": None,
                "status": "active",
            }
        ]
    }


def test_get_live_agents() -> None:
    stub = LiveTopologyStubClient()
    app.dependency_overrides[live_topology_endpoint._client] = lambda: stub

    try:
        client = TestClient(app)
        response = client.get("/api/v1/live_topology/agents")
    finally:
        app.dependency_overrides.pop(live_topology_endpoint._client, None)

    assert response.status_code == 200
    assert response.json() == {
        "agents": [
            {
                "agent_name": "planner",
                "start_time": "2026-07-13T10:01:00Z",
                "end_time": "2026-07-13T10:02:00Z",
                "status": "completed",
            }
        ]
    }


def test_get_live_tools() -> None:
    stub = LiveTopologyStubClient()
    app.dependency_overrides[live_topology_endpoint._client] = lambda: stub

    try:
        client = TestClient(app)
        response = client.get("/api/v1/live_topology/tools")
    finally:
        app.dependency_overrides.pop(live_topology_endpoint._client, None)

    assert response.status_code == 200
    assert response.json() == {
        "tools": [
            {
                "tool_name": "search_docs",
                "start_time": "2026-07-13T10:01:30Z",
                "end_time": None,
                "status": "active",
            }
        ]
    }


def test_get_realtime_topology() -> None:
    stub = LiveTopologyStubClient()
    app.dependency_overrides[live_topology_endpoint._client] = lambda: stub

    try:
        client = TestClient(app)
        response = client.get("/api/v1/live_topology/sessions/session-123/topology")
    finally:
        app.dependency_overrides.pop(live_topology_endpoint._client, None)

    assert response.status_code == 200
    assert stub.requested_session_id == "session-123"
    assert response.json() == {
        "session_id": "session-123",
        "session_status": "active",
        "nodes": [
            {
                "id": "planner",
                "name": "planner",
                "type": "agent",
                "status": "active",
                "start_time": "2026-07-13T10:01:00Z",
                "end_time": None,
                "description": None,
                "data": {"tools": ["search_docs"]},
            },
            {
                "id": "search_docs",
                "name": "search_docs",
                "type": "tool",
                "status": "completed",
                "start_time": "2026-07-13T10:01:30Z",
                "end_time": "2026-07-13T10:01:45Z",
                "description": None,
                "data": None,
            },
        ],
        "edges": [
            {
                "source": "planner",
                "target": "search_docs",
                "label": "invokes",
            }
        ],
        "last_updated": "2026-07-13T10:03:00Z",
    }


class _LiveTopologyFakeDB:
    def __init__(
        self,
        *,
        sessions_rows: list[tuple],
        orphan_rows: list[tuple],
    ) -> None:
        self._sessions_rows = sessions_rows
        self._orphan_rows = orphan_rows
        self.commands: list[tuple[str, dict | None]] = []
        self.emit_should_fail = False

    def execute(self, query, params=None):
        if query == "orphans_stmt":
            return self._orphan_rows
        if query == "sessions_stmt":
            return self._sessions_rows
        raise AssertionError(f"Unexpected query: {query!r}")

    def execute_command(self, command: str, params=None) -> None:
        if self.emit_should_fail:
            raise RuntimeError("simulated ClickHouse write failure")
        self.commands.append((command, params))


def _install_query_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "oxp.query_builders.live_topology.get_orphan_live_topology_sessions",
        lambda dialect: "orphans_stmt",
    )
    monkeypatch.setattr(
        "oxp.query_builders.live_topology.get_live_topology_sessions",
        lambda dialect: "sessions_stmt",
    )


def _make_client(fake_db: _LiveTopologyFakeDB) -> LiveTopologyClient:
    client = LiveTopologyClient()
    client.db = fake_db
    client._dialect = Dialect.SQLITE
    return client


def test_reconciles_stale_orphan_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_query_stubs(monkeypatch)
    fake_db = _LiveTopologyFakeDB(
        sessions_rows=[("session-orphan", "2026-07-14T09:00:00Z", 0, None)],
        orphan_rows=[("session-orphan", "2020-01-01T00:00:00Z", 1, 0)],
    )

    client = _make_client(fake_db)
    response = client.get_live_topology_sessions()

    assert len(fake_db.commands) == 1
    assert response.sessions[0].session_id == "session-orphan"
    assert response.sessions[0].status == "completed"
    # end_time should be populated from the synthetic completion timestamp.
    assert response.sessions[0].end_time is not None


def test_keeps_recent_orphan_sessions_active(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_query_stubs(monkeypatch)
    fake_db = _LiveTopologyFakeDB(
        sessions_rows=[("session-recent", "2026-07-14T10:00:00Z", 0, None)],
        orphan_rows=[("session-recent", "2099-01-01T00:00:00Z", 1, 0)],
    )

    client = _make_client(fake_db)
    response = client.get_live_topology_sessions()

    assert fake_db.commands == []
    assert response.sessions[0].session_id == "session-recent"
    assert response.sessions[0].status == "active"
    assert response.sessions[0].end_time is None


def test_dedupes_repeated_emissions_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second call within the dedupe window must not re-emit for same session."""
    _install_query_stubs(monkeypatch)
    fake_db = _LiveTopologyFakeDB(
        sessions_rows=[("session-orphan", "2026-07-14T09:00:00Z", 0, None)],
        orphan_rows=[("session-orphan", "2020-01-01T00:00:00Z", 1, 0)],
    )

    client = _make_client(fake_db)

    first = client.get_live_topology_sessions()
    second = client.get_live_topology_sessions()

    assert len(fake_db.commands) == 1
    assert first.sessions[0].status == "completed"
    # Second call: no additional write, but sessions_rows still shows uncompleted
    # (simulating the DB not yet reflecting the write). Since we skipped due to
    # dedupe cache, the row status stays "active" — that's expected and safe:
    # the next call after the DB catches up will show completed naturally.
    assert second.sessions[0].status == "active"


def test_caps_emissions_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_query_stubs(monkeypatch)
    orphan_rows = [
        (f"session-{i}", "2020-01-01T00:00:00Z", 1, 0)
        for i in range(LiveTopologyClient._MAX_ORPHAN_EMISSIONS_PER_CALL + 5)
    ]
    fake_db = _LiveTopologyFakeDB(
        sessions_rows=[],
        orphan_rows=orphan_rows,
    )

    client = _make_client(fake_db)
    client.get_live_topology_sessions()

    assert len(fake_db.commands) == LiveTopologyClient._MAX_ORPHAN_EMISSIONS_PER_CALL


def test_ignores_orphans_with_unparseable_last_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_query_stubs(monkeypatch)
    fake_db = _LiveTopologyFakeDB(
        sessions_rows=[("session-orphan", "2026-07-14T09:00:00Z", 0, None)],
        orphan_rows=[("session-orphan", "not-a-date", 1, 0)],
    )

    client = _make_client(fake_db)
    response = client.get_live_topology_sessions()

    assert fake_db.commands == []
    assert response.sessions[0].status == "active"


def test_write_failure_does_not_patch_row(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_query_stubs(monkeypatch)
    fake_db = _LiveTopologyFakeDB(
        sessions_rows=[("session-orphan", "2026-07-14T09:00:00Z", 0, None)],
        orphan_rows=[("session-orphan", "2020-01-01T00:00:00Z", 1, 0)],
    )
    fake_db.emit_should_fail = True

    client = _make_client(fake_db)
    response = client.get_live_topology_sessions()

    assert fake_db.commands == []
    assert response.sessions[0].status == "active"
