#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from oxp.client._sessions import SessionsClient
from oxp.client.local import LocalClient


@pytest.fixture
def connectors(monkeypatch):
    db, kg, provider = Mock(), Mock(), Mock()
    monkeypatch.setattr("oxp.connectors.clickhouse.ClickHouseConnector", db)
    monkeypatch.setattr("oxp.connectors.neo4j.Neo4JConnector", kg)
    monkeypatch.setattr("oxp.providers.OXPMetricsProvider", provider)
    monkeypatch.setattr(
        "oxp.core.config.settings",
        SimpleNamespace(
            **{
                f"{prefix}_{field}": "test"
                for prefix in ("CLICKHOUSE", "NEO4J")
                for field in ("HOST", "PORT", "USERNAME", "PASSWORD", "DATABASE")
            }
        ),
    )
    return db, kg, provider


@pytest.mark.parametrize("persist_metrics", [False, True])
def test_settings_client_closes_its_connections_once_on_error(
    connectors, persist_metrics
):
    db, kg, provider = connectors
    with pytest.raises(RuntimeError, match="query failed"):
        with LocalClient.from_settings(persist_metrics=persist_metrics) as client:
            assert client.db is db.return_value
            raise RuntimeError("query failed")
    client.close()
    db.return_value.close.assert_called_once()
    if persist_metrics:
        provider.assert_called_once_with(db=kg.return_value)
        kg.return_value.close.assert_called_once()
    else:
        kg.assert_not_called()


@pytest.mark.parametrize("persist_metrics", [False, True])
def test_settings_client_cleans_up_when_construction_fails(connectors, persist_metrics):
    db, kg, provider = connectors
    provider.side_effect = RuntimeError("provider failed")
    with pytest.raises(RuntimeError, match="provider failed"):
        LocalClient.from_settings(persist_metrics=persist_metrics)
    db.return_value.close.assert_called_once()
    if persist_metrics:
        kg.return_value.close.assert_called_once()


def test_injected_neo4j_connector_is_reused_and_left_open(connectors):
    db, kg, provider = connectors
    shared = Mock()
    with LocalClient.from_settings(persist_metrics=True, neo4j=shared):
        pass
    kg.assert_not_called()
    provider.assert_called_once_with(db=shared)
    shared.close.assert_not_called()
    db.return_value.close.assert_called_once()


def test_injected_neo4j_connector_is_unused_without_persist_metrics(connectors):
    db, kg, provider = connectors
    shared = Mock()
    LocalClient.from_settings(persist_metrics=False, neo4j=shared).close()
    kg.assert_not_called()
    provider.assert_called_once_with(db=db.return_value)
    shared.close.assert_not_called()


def test_external_connections_are_not_closed():
    db, provider = Mock(), Mock()
    with LocalClient(db=db, metrics_provider=provider):
        pass
    db.close.assert_not_called()
    provider.close.assert_not_called()


@pytest.mark.parametrize("count", [0, 1, 500, 501, 1000])
def test_session_iterator_reads_all_pages(count):
    client = SessionsClient()
    spans = [object() for _ in range(count)]
    client.get_session_spans = Mock(
        side_effect=lambda **kw: SimpleNamespace(
            spans=spans[kw["offset"] : kw["offset"] + kw["limit"]]
        )
    )
    assert list(client.iter_session_spans("session")) == spans
    assert client.get_session_spans.call_args_list == [
        call(session_ids=["session"], limit=500, offset=offset, order="asc")
        for offset in range(0, count + 1, 500)
    ]


@pytest.mark.parametrize(
    "session_id,page_size", [("", 500), (" ", 500), ("s", 0), ("s", -1)]
)
def test_session_iterator_validates_query(session_id, page_size):
    client = SessionsClient()
    client.get_session_spans = Mock()
    with pytest.raises(ValueError):
        list(client.iter_session_spans(session_id, page_size=page_size))
    client.get_session_spans.assert_not_called()


def test_session_iterator_propagates_page_errors():
    client = SessionsClient()
    client.get_session_spans = Mock(
        side_effect=[
            SimpleNamespace(spans=[object()] * 2),
            RuntimeError("database unavailable"),
        ]
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        list(client.iter_session_spans("session", page_size=2))
