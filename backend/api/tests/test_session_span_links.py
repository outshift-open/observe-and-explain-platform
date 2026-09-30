#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from oxp.client._sessions import SessionsClient
from oxp.query_builders.sessions import session_spans_query
from oxp.query_builders.types import Dialect


class _RowsConnector:
    def execute(self, _statement):
        return [
            (
                "span-child",
                "session-1",
                "agent.chat",
                "2026-09-14T00:00:01Z",
                12,
                "OK",
                "span-parent",
                "coordination-service",
                '{"session.id": "session-1"}',
                '["trace-1"]',
                ["span-peer"],
                "[]",
                '[{"mas.link.type": "peer_message"}]',
            )
        ]


def test_session_spans_preserve_otel_links() -> None:
    client = SessionsClient()
    client.db = _RowsConnector()
    client._dialect = Dialect.SQLITE

    result = client.get_session_spans(session_ids=["session-1"])

    span = result.spans[0]
    assert span.links_trace_id == ["trace-1"]
    assert span.links_span_id == ["span-peer"]
    assert span.links_trace_state == []
    assert span.links_attributes == [{"mas.link.type": "peer_message"}]


def test_session_span_pagination_has_stable_tie_breaker() -> None:
    for order, direction in (("asc", "ASC"), ("desc", "DESC")):
        query = session_spans_query(Dialect.SQLITE, order=order, limit=500, offset=500)
        sql = str(query)
        assert (
            f"ORDER BY otel_traces.timestamp {direction}, otel_traces.span_id {direction}"
            in sql
        )
