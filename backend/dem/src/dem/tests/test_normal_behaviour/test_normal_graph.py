#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import networkx as nx
from dem.normal_behaviour.normal_graph import GraphNormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourResultGraph
from dem.utils.graph_utils import execution_graph_to_nx_graph


def make_graph(edges):
    G = nx.DiGraph()
    G.add_edges_from(edges)
    return G


def asses_graph_normal_behaviour(candidate_graph, expected_graph, closest_sample=None):
    assert isinstance(candidate_graph, NormalBehaviourResultGraph)
    g = execution_graph_to_nx_graph(candidate_graph.centroid)
    assert isinstance(g, nx.DiGraph), "Centroid should be a graph"

    # Check if the candidate graph is isomorphic to the expected graph
    assert nx.is_isomorphic(g, expected_graph), (
        "Candidate graph should be isomorphic to the centroid graph"
    )

    g = execution_graph_to_nx_graph(candidate_graph.representative_sample)
    assert isinstance(g, nx.DiGraph), "Representative sample should be a graph"

    if closest_sample is not None:
        # Check if the candidate graph is isomorphic to the closest sample
        print("Candidate graph nodes:", g.nodes(), "edges:", g.edges())
        print(
            "Closest sample nodes:",
            closest_sample.nodes(),
            "edges:",
            closest_sample.edges(),
        )
        assert nx.is_isomorphic(g, closest_sample), (
            "Candidate graph should be isomorphic to the closest sample"
        )
    else:
        # If no closest sample is provided, the representative sample should be the same as the centroid
        assert nx.is_isomorphic(g, expected_graph), (
            "Candidate graph should be isomorphic to the expected graph"
        )

    if candidate_graph.other_info is not None:
        if "medoid_distances" in candidate_graph.other_info:
            assert isinstance(candidate_graph.other_info["medoid_distances"], list)
            assert all(
                isinstance(d, float)
                for d in candidate_graph.other_info["medoid_distances"]
            )


def test_medoid_graph():
    # Create 3 simple graphs
    g1 = make_graph([(1, 2), (2, 3)])
    g2 = make_graph([(1, 2), (2, 3), (3, 4)])
    g3 = make_graph([(1, 2), (2, 3), (4, 5)])
    graphs = [g1, g2, g3]

    nb = GraphNormalBehaviour(statistic="medoid")
    result = nb.calculate_normal_behaviour(graphs)
    asses_graph_normal_behaviour(
        result, g1
    )  # g1 is the medoid graph since it has the smallest total distance to others


def test_consensus_graph():
    # Create 3 simple graphs
    g1 = make_graph([(1, 2), (2, 3)])
    g2 = make_graph([(1, 2), (2, 3), (3, 4)])
    g3 = make_graph([(1, 2), (2, 3), (4, 5)])
    graphs = [g1, g2, g3]

    nb = GraphNormalBehaviour(statistic="consensus")
    result = nb.calculate_normal_behaviour(graphs)
    asses_graph_normal_behaviour(
        result, g1
    )  # g1 is the medoid graph since it has the smallest total distance to others


def test_consensus_graph_closest_sample():
    # Create 3 simple graphs
    g1 = make_graph([(1, 2), (2, 3), [10, 20]])
    g2 = make_graph([(1, 2), (2, 3), (3, 4), (20, 30)])
    g3 = make_graph([(1, 2), (2, 3), (4, 5), (-10, -20)])
    graphs = [g1, g2, g3]
    nb = GraphNormalBehaviour(statistic="consensus")
    result = nb.calculate_normal_behaviour(graphs)

    g_centroid = make_graph(
        [(1, 2), (2, 3)]
    )  # consensus graph is the same as medoid in this case

    asses_graph_normal_behaviour(
        result, g_centroid, g1
    )  # g1 is the medoid graph since it has the smallest total distance to others


def test_empty_graph_list():
    nb = GraphNormalBehaviour(statistic="medoid")
    result = nb.calculate_normal_behaviour([])
    assert isinstance(result, NormalBehaviourResultGraph)
    assert result.statistic == "", (
        "Statistic description should be empty for empty input"
    )
    assert result.representative_sample is None, (
        "Representative data should be None for empty input"
    )
    assert result.other_info is None, "Other info should be None for empty input"
