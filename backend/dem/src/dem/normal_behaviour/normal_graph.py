#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import List
import networkx as nx
import numpy as np
from collections import Counter

from dem.normal_behaviour.base import NormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourResultGraph
from dem.utils import setup_logger
from dem.utils.graph_utils import nx_graph_to_dict

logger = setup_logger(__name__)

# TODO add labels / nodes type


class GraphNormalBehaviour(NormalBehaviour):
    def __init__(
        self,
        statistic: str,
        majority_threshold: float = 0.5,  # only used for consensus, can be set in config
        get_closest_sample: bool = True,  # only used for consensus, to compute the closest sample to the consensus graph
    ):
        super().__init__(statistic)
        self.majority_threshold = majority_threshold
        self.get_closest_sample = get_closest_sample

    def calculate_normal_behaviour(
        self,
        data: List[nx.Graph],
    ) -> NormalBehaviourResultGraph:
        if not data:
            return NormalBehaviourResultGraph()

        result = NormalBehaviourResultGraph()
        match self.statistic:
            case "medoid":
                medoid_idx, medoid_graph, medoid_distances = self._find_medoid_graph(
                    data
                )
                result.statistic = "medoid"
                result.representative_sample = nx_graph_to_dict(medoid_graph)
                result.centroid = (
                    result.representative_sample
                )  # the centroid is the same as the representative sample for medoid
                result.other_info = {
                    "medoid_distances": medoid_distances,
                    "medoid_index": medoid_idx,
                }
            case "consensus":
                result.statistic = "consensus"
                consensus_graph, closest_sample = self._consensus_graph(
                    data,
                    majority_threshold=self.majority_threshold,
                    compute_closest=self.get_closest_sample,
                )
                result.centroid = nx_graph_to_dict(consensus_graph)
                if closest_sample is not None:
                    result.representative_sample = nx_graph_to_dict(closest_sample)
            case _:
                raise ValueError(f"Unsupported statistic: {self.statistic}")

        return result

    def _graph_distance(self, g1, g2):
        # Use a simple graph edit distance (can be replaced with WL or other metrics)
        try:
            return nx.graph_edit_distance(g1, g2)
        except Exception as e:
            logger.warning(f"Graph edit distance failed: {e}")
            return float("inf")

    def _find_medoid_graph(self, graphs):
        n = len(graphs)
        dist_matrix = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = self._graph_distance(graphs[i], graphs[j])
                dist_matrix[i, j] = dist_matrix[j, i] = d
        sum_dist = dist_matrix.sum(axis=1)
        medoid_idx = int(np.argmin(sum_dist))
        return medoid_idx, graphs[medoid_idx], dist_matrix[medoid_idx].tolist()

    def _consensus_graph(self, graphs, majority_threshold=0.5, compute_closest=False):
        # Consensus: keep edges that appear in >50% of graphs; nodes only if part of consensus edges
        edge_counter = Counter()
        n_graphs = len(graphs)
        for g in graphs:
            edge_counter.update([(u, v) for u, v in g.edges()])
        consensus_edges = [
            e for e, c in edge_counter.items() if c > n_graphs * majority_threshold
        ]
        consensus_nodes = set()
        for u, v in consensus_edges:
            consensus_nodes.add(u)
            consensus_nodes.add(v)
        G = nx.DiGraph()
        G.add_nodes_from(consensus_nodes)
        G.add_edges_from(consensus_edges)

        if compute_closest:
            # Find the graph closest to the consensus (using edit distance)
            min_dist = float("inf")
            closest_graph = None
            for g in graphs:
                d = self._graph_distance(G, g)

                if d < min_dist:
                    min_dist = d
                    closest_graph = g
            return G, closest_graph
        else:
            return G, None
