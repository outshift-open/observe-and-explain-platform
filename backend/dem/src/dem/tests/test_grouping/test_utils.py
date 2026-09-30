#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import AsyncMock, MagicMock

import pytest

from dem.grouping import Hierarchy, SemanticGroup


@pytest.fixture
def sample_hierarchy_data():
    return [
        {"id": "root", "children_nodes": ["child_1", "child_2"], "split_distance": 0.5},
        {
            "id": "child_1",
            "session_ids": ["s1", "s2"],
            "children_nodes": [],
            "split_distance": 0.1,
        },
        {
            "id": "child_2",
            "session_ids": ["s3"],
            "children_nodes": [],
            "split_distance": 0.1,
        },
    ]


def test_semantic_group_is_leaf():
    leaf = SemanticGroup(id="L", children_nodes=[])
    internal = SemanticGroup(id="I", children_nodes=["L"])
    assert leaf.is_leaf is True
    assert internal.is_leaf is False


def test_hierarchy_from_list(sample_hierarchy_data):
    h = Hierarchy.from_list(sample_hierarchy_data)
    assert len(h) == 3
    assert "root" in h.nodes
    assert h.nodes["child_1"].session_ids == ["s1", "s2"]


def test_get_all_sessions(sample_hierarchy_data):
    h = Hierarchy.from_list(sample_hierarchy_data)
    root_sessions = h.get_all_sessions("root")
    assert root_sessions == {"s1", "s2", "s3"}
    # Check cache
    assert "root" in h._session_cache


def test_collapse_node(sample_hierarchy_data):
    h = Hierarchy.from_list(sample_hierarchy_data)
    h.collapse_node("root")

    assert len(h) == 1
    assert h.nodes["root"].is_leaf is True
    assert set(h.nodes["root"].session_ids) == {"s1", "s2", "s3"}
    assert h.nodes["root"].n_sessions == 3


def test_rename_node_and_propagate(sample_hierarchy_data):
    h = Hierarchy.from_list(sample_hierarchy_data)
    h._rename_node_and_propagate("child_1", "new_child_1")

    assert "new_child_1" in h.nodes
    assert "child_1" not in h.nodes
    assert "new_child_1" in h.nodes["root"].children_nodes
    assert "child_1" not in h.nodes["root"].children_nodes


def test_merge_ids_from_previous_jaccard():
    # Previous state
    prev_data = [
        {
            "id": "old_id_123",
            "session_ids": ["s1", "s2", "s3", "s4", "s5", "s6"],
            "group_name": "Legacy Name",
        }
    ]
    prev_h = Hierarchy.from_list(prev_data)

    # Current state (different ID, same sessions)
    curr_data = [
        {
            "id": "new_id_456",
            "session_ids": ["s1", "s2", "s3", "s4", "s5", "s6", "s7"],
        }
    ]
    curr_h = Hierarchy.from_list(curr_data)

    curr_h.merge_ids_from_previous(prev_h, embeddings={})

    assert "old_id_123" in curr_h.nodes
    assert curr_h.nodes["old_id_123"].group_name == "Legacy Name"


def test_add_missing_group_names():
    h = Hierarchy.from_list([{"id": "node1", "session_ids": ["s1", "s2"]}])
    mock_llm = MagicMock()
    mock_llm.process_nodes_batch = AsyncMock(
        return_value={"node1": ("Generated Name", "Generated Summary")}
    )

    queries = {"s1": "question 1?", "s2": "question 2?"}
    import asyncio

    asyncio.run(h.add_missing_group_names(queries, mock_llm))

    assert h.nodes["node1"].group_name == "Generated Name"
