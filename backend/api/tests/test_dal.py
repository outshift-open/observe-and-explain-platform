#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for DAL functions in oxp/client/dal.py.

Run with:
    pytest tests/test_dal.py -v -s

Requires a running Neo4j instance.  Connection details are read from environment
variables (defaults shown):

    NEO4J_HOST      localhost
    NEO4J_PORT      7687
    NEO4J_USERNAME  neo4j
    NEO4J_PASSWORD  (empty)
    NEO4J_DATABASE  neo4j
"""

from __future__ import annotations

import logging
import os
import sys

import pytest
from dotenv import load_dotenv

from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client.dal import get_session_io, get_state_content
from oxp.connectors.neo4j import Neo4JConnector

load_dotenv()

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so ``oxp`` is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Module-scoped connector ───────────────────────────────────────────────────

_connector: Neo4JConnector | None = None


def _get_connector() -> Neo4JConnector:
    """Lazily create a module-level Neo4j connector."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        host = os.environ.get("NEO4J_HOST") or "localhost"
        port = int(os.environ.get("NEO4J_PORT") or "7687")
        username = os.environ.get("NEO4J_USERNAME") or "neo4j"
        password = os.environ.get("NEO4J_PASSWORD") or ""
        database = os.environ.get("NEO4J_DATABASE") or "neo4j"

        logger.info(
            "Using Neo4J connector — %s:%s/%s",
            host,
            port,
            database,
        )
        _connector = Neo4JConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
        _connector.connect()
        if not _connector.is_connected():
            raise RuntimeError(
                "Neo4j connection/authentication failed for tests. "
                "Set valid NEO4J_* environment variables."
            )
    return _connector


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Connect once for the module and close after all tests finish."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def neo4j_db():
    """Provide the shared Neo4JConnector for the test database."""
    return _get_connector()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDalFunctions:
    """Exercise ``get_state_content`` against a live Neo4j instance."""

    def test_get_state_content(self, neo4j_db) -> None:
        result = get_state_content(
            neo4j_db,
            filters_eq={"sessionId": "3e376241-163b-4f78-babf-4b6b054d734f"},
            filters_neq={"content": ""},
        )

        logger.info("get_state_content → %d item(s)", len(result))
        assert isinstance(result, list)

        for r in result:
            print(r)

    def test_get_session_io(self, neo4j_db) -> None:
        result = get_session_io(
            neo4j_db,
            session_id="3e376241-163b-4f78-babf-4b6b054d734f",
        )

        logger.info("get_session_io → %d item(s)", len(result))
        assert isinstance(result, list)

        for r in result:
            print(r)

    # # ── no-filter query ───────────────────────────────────────────────────────

    # def test_returns_list(self, neo4j_db) -> None:
    #     """get_state_content always returns a list (possibly empty)."""
    #     result = get_state_content(neo4j_db, filters_eq={}, filters_neq={})

    #     logger.info("get_state_content(no filters) → %d item(s)", len(result))
    #     assert isinstance(result, list)

    # def test_items_have_required_keys(self, neo4j_db) -> None:
    #     """Every returned item must have 'id' and 'content' keys."""
    #     result = get_state_content(neo4j_db, filters_eq={}, filters_neq={})

    #     for item in result:
    #         assert "id" in item, f"Missing 'id' key in {item!r}"
    #         assert "content" in item, f"Missing 'content' key in {item!r}"
    #         assert isinstance(item["id"], str)
    #         assert isinstance(item["content"], str)

    #     logger.info(
    #         "get_state_content(no filters) — %d item(s) validated", len(result)
    #     )

    # # ── equality filter ───────────────────────────────────────────────────────

    # def test_equality_filter_narrows_results(self, neo4j_db) -> None:
    #     """Results filtered by a known stateId are a subset of the full list."""
    #     all_states = get_state_content(neo4j_db, filters_eq={}, filters_neq={})

    #     if not all_states:
    #         pytest.skip("No State nodes in database — skipping filter test")

    #     # Pick the first stateId that is non-empty
    #     target_id = next(
    #         (s["id"] for s in all_states if s["id"]),
    #         None,
    #     )
    #     if not target_id:
    #         pytest.skip("No State node with a non-empty stateId — skipping filter test")

    #     filtered = get_state_content(
    #         neo4j_db,
    #         filters_eq={"stateId": target_id},
    #         filters_neq={},
    #     )

    #     logger.info(
    #         "Filtered by stateId=%r → %d item(s) (total was %d)",
    #         target_id,
    #         len(filtered),
    #         len(all_states),
    #     )

    #     assert len(filtered) >= 1, "Equality filter should return at least one item"
    #     assert len(filtered) <= len(all_states), "Filtered set must be ≤ total set"
    #     assert all(s["id"] == target_id for s in filtered), (
    #         "All returned items must match the equality filter"
    #     )

    # # ── inequality filter ─────────────────────────────────────────────────────

    # def test_inequality_filter_excludes_item(self, neo4j_db) -> None:
    #     """Results with a neq filter must not contain the excluded stateId."""
    #     all_states = get_state_content(neo4j_db, filters_eq={}, filters_neq={})

    #     if len(all_states) < 2:
    #         pytest.skip("Need at least 2 State nodes to test neq filter")

    #     exclude_id = next(
    #         (s["id"] for s in all_states if s["id"]),
    #         None,
    #     )
    #     if not exclude_id:
    #         pytest.skip("No State node with a non-empty stateId — skipping neq test")

    #     filtered = get_state_content(
    #         neo4j_db,
    #         filters_eq={},
    #         filters_neq={"stateId": exclude_id},
    #     )

    #     logger.info(
    #         "Excluded stateId=%r → %d item(s) remain (total was %d)",
    #         exclude_id,
    #         len(filtered),
    #         len(all_states),
    #     )

    #     assert all(s["id"] != exclude_id for s in filtered), (
    #         "Excluded stateId must not appear in neq-filtered results"
    #     )

    # # ── combined filters ──────────────────────────────────────────────────────

    # def test_combined_eq_and_neq_filters(self, neo4j_db) -> None:
    #     """Combining eq and neq filters applies both constraints."""
    #     all_states = get_state_content(neo4j_db, filters_eq={}, filters_neq={})

    #     if len(all_states) < 2:
    #         pytest.skip("Need at least 2 State nodes for combined-filter test")

    #     ids_with_content = [s for s in all_states if s["id"] and s["content"]]
    #     if len(ids_with_content) < 2:
    #         pytest.skip("Need at least 2 State nodes with non-empty id+content")

    #     target_id = ids_with_content[0]["id"]
    #     exclude_id = ids_with_content[1]["id"]
    #     target_content = ids_with_content[0]["content"]

    #     filtered = get_state_content(
    #         neo4j_db,
    #         filters_eq={"content": target_content},
    #         filters_neq={"stateId": exclude_id},
    #     )

    #     logger.info(
    #         "Combined filter: content=%r, stateId≠%r → %d item(s)",
    #         target_content,
    #         exclude_id,
    #         len(filtered),
    #     )

    #     for item in filtered:
    #         assert item["content"] == target_content, (
    #             "eq filter must be respected"
    #         )
    #         assert item["id"] != exclude_id, (
    #             "neq filter must be respected"
    #         )

    # # ── non-existent filter ───────────────────────────────────────────────────

    # def test_no_match_returns_empty_list(self, neo4j_db) -> None:
    #     """A filter that matches nothing must return an empty list, not raise."""
    #     result = get_state_content(
    #         neo4j_db,
    #         filters_eq={"stateId": "__no_such_state_id__"},
    #         filters_neq={},
    #     )

    #     logger.info("Non-matching filter → %d item(s)", len(result))
    #     assert result == [], "Expected empty list for a non-matching filter"

    # # ── error handling ────────────────────────────────────────────────────────

    # def test_bad_connector_raises_database_error(self) -> None:
    #     """A broken connector must cause DatabaseError, not a raw driver exception."""
    #     bad_db = Neo4JConnector(
    #         host="localhost",
    #         port=19999,  # nothing listening here
    #         username="neo4j",
    #         password="wrong",
    #         database="neo4j",
    #     )
    #     with pytest.raises((DatabaseError, Exception)):
    #         get_state_content(bad_db, filters_eq={}, filters_neq={})
