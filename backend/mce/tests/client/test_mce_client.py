#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.client package."""

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# MCEClientConfig
# ---------------------------------------------------------------------------


def test_config_default_constructor_is_explicit(monkeypatch):
    """Default construction should not pull Neo4j settings from ambient env."""
    monkeypatch.setenv("KG_DB_HOST", "bolt://testhost:7687")
    monkeypatch.setenv("KG_DB_USER", "testuser")
    monkeypatch.setenv("KG_DB_PASSWORD", "testpass")
    from mce.client.config import MCEClientConfig

    cfg = MCEClientConfig()
    assert cfg.kg_host is None
    assert cfg.kg_user is None
    assert cfg.kg_password is None


def test_config_from_env(monkeypatch):
    """CLI/API boundaries can still translate env vars into explicit config."""
    monkeypatch.setenv("KG_DB_HOST", "bolt://testhost:7687")
    monkeypatch.setenv("KG_DB_USER", "testuser")
    monkeypatch.setenv("KG_DB_PASSWORD", "testpass")
    monkeypatch.setenv("NEO4J_DATABASE", "analytics")

    from mce.client.config import MCEClientConfig

    cfg = MCEClientConfig.from_env()
    assert cfg.kg_host == "bolt://testhost:7687"
    assert cfg.kg_user == "testuser"
    assert cfg.kg_password == "testpass"
    assert cfg.kg_database == "analytics"


def test_build_api_graph_provider_forwards_kg_connection_config():
    from mce.client.client import _build_api_graph_provider
    from mce.client.config import MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687",
        kg_user="neo4j",
        kg_password="x",
        kg_database="neo4j",
    )

    with patch("oxp.providers.Neo4jGraphProvider") as mock_provider:
        _build_api_graph_provider(cfg)

    _, kwargs = mock_provider.call_args
    assert kwargs["host"] == "bolt://localhost:7687"
    assert kwargs["username"] == "neo4j"
    assert kwargs["password"] == "x"
    assert kwargs["database"] == "neo4j"
    assert "workarounds" not in kwargs


def test_config_validate_raises_without_password():
    """validate() raises ValueError when password is missing."""
    from mce.client.config import MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687", kg_user="neo4j", kg_password=None
    )
    with pytest.raises(ValueError, match="password"):
        cfg.validate()


def test_config_validate_passes_with_password():
    from mce.client.config import MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687", kg_user="neo4j", kg_password="secret"
    )
    cfg.validate()  # should not raise


# ---------------------------------------------------------------------------
# MCEClient
# ---------------------------------------------------------------------------


def test_client_instantiates_with_explicit_config():
    from mce.client import MCEClient, MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687", kg_user="neo4j", kg_password="x"
    )
    client = MCEClient(config=cfg)
    assert client._config is cfg


def test_client_lazy_kg_provider():
    """KG provider is not created until first call."""
    from mce.client import MCEClient, MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687", kg_user="neo4j", kg_password="x"
    )
    client = MCEClient(config=cfg)
    assert client._kg_provider is None  # not yet initialised


def test_client_context_manager():
    """MCEClient can be used as a context manager."""
    from mce.client import MCEClient, MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687", kg_user="neo4j", kg_password="x"
    )
    with MCEClient(config=cfg) as client:
        assert client is not None
    # After __exit__, _kg_provider should be None
    assert client._kg_provider is None


def test_client_close_is_idempotent():
    from mce.client import MCEClient, MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687", kg_user="neo4j", kg_password="x"
    )
    client = MCEClient(config=cfg)
    client.close()
    client.close()  # second close must not raise


def test_client_builds_oxp_api_provider_from_explicit_config():
    from mce.client import MCEClient, MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687",
        kg_user="neo4j",
        kg_password="x",
        kg_database="neo4j",
    )

    with patch("mce.client.client._build_api_graph_provider") as mock_provider:
        client = MCEClient(config=cfg)
        provider = client._get_kg_provider()

    mock_provider.assert_called_once_with(cfg)
    assert provider is mock_provider.return_value


def test_client_compute_and_store_preserves_explicit_config():
    from mce.client import MCEClient, MCEClientConfig

    cfg = MCEClientConfig(
        kg_host="bolt://localhost:7687",
        kg_user="neo4j",
        kg_password="x",
        kg_database="neo4j",
    )

    with patch("mce.client.worker.MCEWorkerService") as mock_service:
        mock_service.return_value.process_session.return_value = []
        client = MCEClient(config=cfg)
        client.compute_and_store("session-1")

    mock_service.assert_called_once_with(kg_provider=None, client_config=cfg)
