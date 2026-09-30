#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
import numpy as np
from typing import Dict
from dem.grouping import Hierarchy, SemanticGrouper


@pytest.fixture
def mock_embeddings() -> Dict[str, np.ndarray]:
    return {
        "s1": np.array([1.0, 0.0, 0.0]),
        "s2": np.array([1.0, 0.1, 0.0]),
        "s3": np.array([0.0, 1.0, 0.0]),
        "s4": np.array([0.0, 1.1, 0.0]),
        "s5": np.array([0.5, 0.5, 0.5]),
    }


@pytest.fixture
def simple_hierarchy_list():
    return [
        {
            "id": "root",
            "children_nodes": ["child_a", "child_b"],
            "session_ids": [],
            "split_distance": 0.5,
        },
        {
            "id": "child_a",
            "children_nodes": [],
            "session_ids": ["s1", "s2"],
            "medioid_session_id": "s1",
            "split_distance": 0.1,
        },
        {
            "id": "child_b",
            "children_nodes": [],
            "session_ids": ["s3", "s4"],
            "medioid_session_id": "s3",
            "split_distance": 0.1,
        },
    ]


class TestHierarchyLogic:
    def test_get_all_sessions_recursive(self, simple_hierarchy_list):
        h = Hierarchy.from_list(simple_hierarchy_list)
        root_sessions = h.get_all_sessions("root")
        assert root_sessions == {"s1", "s2", "s3", "s4"}
        assert h.get_all_sessions("child_a") == {"s1", "s2"}

    def test_collapse_node(self, simple_hierarchy_list):
        h = Hierarchy.from_list(simple_hierarchy_list)
        h.collapse_node("root")

        # Root should now be a leaf
        assert h.nodes["root"].is_leaf
        assert set(h.nodes["root"].session_ids) == {"s1", "s2", "s3", "s4"}
        assert h.nodes["root"].n_sessions == 4
        # Children should be removed from the dict
        assert "child_a" not in h.nodes
        assert "child_b" not in h.nodes

    def test_rename_node_and_propagate(self, simple_hierarchy_list):
        h = Hierarchy.from_list(simple_hierarchy_list)
        h._rename_node_and_propagate("child_a", "NEW_ID_A")

        # Check dict key changed
        assert "NEW_ID_A" in h.nodes
        assert "child_a" not in h.nodes
        # Check parent reference updated
        assert "NEW_ID_A" in h.nodes["root"].children_nodes
        assert "child_a" not in h.nodes["root"].children_nodes

    def test_merge_by_jaccard(self, simple_hierarchy_list, mock_embeddings):
        # Create a "previous" hierarchy with names
        prev_list = [
            {
                "id": "PREV_ROOT",
                "children_nodes": [],
                "session_ids": ["s1", "s2", "s3", "s4"],
                "group_name": "Old Root Name",
            }
        ]
        prev_h = Hierarchy.from_list(prev_list)

        # Create "new" hierarchy
        new_h = Hierarchy.from_list(simple_hierarchy_list)

        # Merge - the 'root' in new_h matches 'PREV_ROOT' in prev_h via Jaccard
        new_h.merge_ids_from_previous(prev_h, mock_embeddings, jaccard_threshold=0.9)

        # 'root' should have been renamed to 'PREV_ROOT' and got the name
        assert "PREV_ROOT" in new_h.nodes
        assert new_h.nodes["PREV_ROOT"].group_name == "Old Root Name"

    def test_merge_by_embedding(self, mock_embeddings):
        # Prev node with specific medioid
        prev_h = Hierarchy.from_list(
            [
                {
                    "id": "OLD_EMB_NODE",
                    "session_ids": ["s5"],
                    "medioid_session_id": "s5",
                    "group_name": "Medioid Match",
                }
            ]
        )

        # New node with different session but SAME medioid
        new_h = Hierarchy.from_list(
            [
                {
                    "id": "NEW_NODE",
                    "session_ids": ["s100"],  # Different session ID
                    "medioid_session_id": "s5",  # Same medioid session
                    "group_name": "",
                }
            ]
        )

        new_h.merge_ids_from_previous(prev_h, mock_embeddings, jaccard_threshold=1.0)

        assert "OLD_EMB_NODE" in new_h.nodes
        assert (
            new_h.nodes["OLD_ID_EMB_NODE" if False else "OLD_EMB_NODE"].group_name
            == "Medioid Match"
        )


class TestSemanticGrouper:
    def test_get_cluster_hierarchy_integration(self, mock_embeddings):
        grouper = SemanticGrouper(max_radius=0.1, min_cluster_size=2)
        hierarchy = grouper.get_cluster_hierarchy(mock_embeddings)

        assert isinstance(hierarchy, Hierarchy)
        assert len(hierarchy.nodes) > 0

        # Verify that all nodes have a medioid assigned
        for node in hierarchy.nodes.values():
            assert node.medioid_session_id != ""
            assert node.medioid_session_id in mock_embeddings

    def test_full_workflow(self, mock_embeddings):
        grouper = SemanticGrouper(max_radius=0.2)

        # 1. First Pass
        h1, _ = grouper.compute_semantic_hierarchy(mock_embeddings)
        # Simulate user naming a group
        some_id = list(h1.nodes.keys())[0]
        h1.nodes[some_id].group_name = "User Defined Name"

        # 2. Second Pass (with same data)
        h2, _ = grouper.compute_semantic_hierarchy(
            mock_embeddings, previous_hierarchy=h1
        )

        # Check if the name survived
        found_name = any(n.group_name == "User Defined Name" for n in h2.nodes.values())
        assert found_name, "Metadata did not propagate to the new hierarchy"
