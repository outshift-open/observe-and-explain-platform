#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_neo4j_uri():
    return "bolt://localhost:7687"


@pytest.fixture
def mock_neo4j_user():
    return "neo4j"


@pytest.fixture
def mock_neo4j_password():
    return "password"


@pytest.fixture
def mock_neo4j_database():
    return "neo4j"


def _create_mock_connector():
    """Create a mock Neo4JConnector that doesn't require a running Neo4j instance."""
    mock_connector = MagicMock()

    # Mock connect and close methods
    mock_connector.connect = MagicMock()
    mock_connector.close = MagicMock()

    # Mock execute method to return sample data
    def mock_execute(query, params=None):
        params = params or {}
        query_lower = query.lower()

        if "state" in query_lower and "content" in query_lower:
            # For get_state_content queries
            return [
                {
                    "id": "state-1",
                    "content": "Sample state content 1",
                },
                {
                    "id": "state-2",
                    "content": "Sample state content 2",
                },
            ]
        elif "count(e)" in query_lower or "rel_count" in query_lower:
            # For relationship count queries
            return [{"rel_count": 1}]
        elif "embedding" in query_lower and "match" in query_lower:
            # For embedding retrieval queries
            embedding_id = params.get("embedding_id")
            # Extract the embedding model from the embedding_id if present
            # Format: {TEST_SESSION_ID}_{state_id}_{embedding_model}
            parts = embedding_id.split("_") if embedding_id else []
            embedding_model = parts[-1] if len(parts) > 0 else "test-model"

            return (
                [
                    {
                        "id": embedding_id,
                        "embeddingModel": embedding_model,
                        "embeddingVector": [0.11, 0.22, 0.33],
                    }
                ]
                if embedding_id
                else []
            )
        else:
            return []

    mock_connector.execute = mock_execute
    mock_connector.execute_command = MagicMock()

    return mock_connector


@pytest.fixture
def mock_neo4j_connector():
    """Mock Neo4JConnector fixture."""
    return _create_mock_connector()


# Automatically patch Neo4JConnector for all tests that import it
@pytest.fixture(autouse=True)
def auto_patch_neo4j_connector(monkeypatch):
    """Patch Neo4JConnector globally so tests don't need a running Neo4j."""

    # Create a class that returns mock connectors
    class MockNeo4JConnectorClass:
        def __init__(self, *args, **kwargs):
            self.mock = _create_mock_connector()

        def __getattr__(self, name):
            return getattr(self.mock, name)

    # Patch in common locations where it might be imported
    patches = [
        "oxp.connectors.neo4j.Neo4JConnector",
        "test_dal_migration.Neo4JConnector",
    ]

    for patch_path in patches:
        try:
            monkeypatch.setattr(patch_path, MockNeo4JConnectorClass)
        except Exception:
            pass  # Module might not be loaded yet

    yield
