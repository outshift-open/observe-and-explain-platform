#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for norm.verifier — one test per structural invariant.

All tests operate on plain dicts; no real KG file required.
Node schema: id, node_type, startTime, endTime.
Edge schema: edge_type, from_id, to_id.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# check_unknown_node_types
# ---------------------------------------------------------------------------


class TestCheckUnknownNodeTypes:
    def test_known_node_type_passes(self):
        from norm.verifier import KNOWN_NODE_TYPES, check_unknown_node_types

        if not KNOWN_NODE_TYPES:
            pytest.skip("Ontology not loaded — KNOWN_NODE_TYPES empty")
        node_type = next(iter(KNOWN_NODE_TYPES))
        nodes = [{"node_type": node_type, "id": "x"}]
        ok, violations = check_unknown_node_types(nodes, [])
        assert ok
        assert violations == []

    def test_unknown_node_type_is_violation(self):
        from norm.verifier import check_unknown_node_types

        nodes = [{"node_type": "CompletelyFakeNodeXYZ", "id": "x"}]
        ok, violations = check_unknown_node_types(nodes, [])
        assert not ok
        assert any("CompletelyFakeNodeXYZ" in str(v) for v in violations)

    def test_missing_node_type_is_violation(self):
        from norm.verifier import check_unknown_node_types

        nodes = [{"id": "x"}]
        ok, violations = check_unknown_node_types(nodes, [])
        assert not ok

    def test_empty_nodes_passes(self):
        from norm.verifier import check_unknown_node_types

        ok, violations = check_unknown_node_types([], [])
        assert ok


# ---------------------------------------------------------------------------
# check_unknown_edge_types
# ---------------------------------------------------------------------------


class TestCheckUnknownEdgeTypes:
    def test_known_edge_type_passes(self):
        from norm.verifier import KNOWN_EDGE_TYPES, check_unknown_edge_types

        if not KNOWN_EDGE_TYPES:
            pytest.skip("Ontology not loaded — KNOWN_EDGE_TYPES empty")
        etype = next(iter(KNOWN_EDGE_TYPES))
        edges = [{"edge_type": etype, "from_id": "a", "to_id": "b"}]
        ok, violations = check_unknown_edge_types([], edges)
        assert ok

    def test_unknown_edge_type_is_violation(self):
        from norm.verifier import check_unknown_edge_types

        edges = [{"edge_type": "completelyFakeEdge", "from_id": "a", "to_id": "b"}]
        ok, violations = check_unknown_edge_types([], edges)
        assert not ok
        assert any("completelyFakeEdge" in str(v) for v in violations)

    def test_missing_edge_type_is_violation(self):
        from norm.verifier import check_unknown_edge_types

        edges = [{"from_id": "a", "to_id": "b"}]  # no edge_type
        ok, violations = check_unknown_edge_types([], edges)
        assert not ok

    def test_empty_edges_passes(self):
        from norm.verifier import check_unknown_edge_types

        ok, _ = check_unknown_edge_types([], [])
        assert ok
