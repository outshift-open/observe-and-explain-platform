#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from collections import Counter
import hashlib
from typing import List

import networkx as nx
import numpy as np

from .base import Consistency
from .utils import ConsistencyResult
from ..utils import setup_logger

logger = setup_logger(__name__)


def get_wl_labels(G, node_attr="agent_id", iterations=4):
    """
    Generates a 'bag of labels' for a graph using the WL algorithm logic.
    """
    labels = {n: str(G.nodes[n].get(node_attr, "")) for n in G.nodes()}
    all_counts = Counter(labels.values())

    for _ in range(iterations):
        new_labels = {}
        for n in G.nodes():
            neighbor_labels = sorted([labels[neighbor] for neighbor in G.neighbors(n)])
            combined = f"{labels[n]}-{''.join(neighbor_labels)}"
            new_labels[n] = hashlib.sha256(combined.encode()).hexdigest()

        labels = new_labels
        all_counts.update(labels.values())

    return all_counts


def wl_distance(G1, G2, node_attr="agent_id", iterations=4):
    """
    Computes the WL distance between two graphs.
    Distance = 1 - (Normalized Dot Product of label counts)
    """
    counts1 = get_wl_labels(G1, node_attr, iterations)
    counts2 = get_wl_labels(G2, node_attr, iterations)

    all_labels = set(counts1.keys()).union(set(counts2.keys()))

    dot_product = 0
    mag1 = 0
    mag2 = 0

    for label in all_labels:
        val1 = counts1.get(label, 0)
        val2 = counts2.get(label, 0)
        dot_product += val1 * val2
        mag1 += val1**2
        mag2 += val2**2

    if mag1 == 0 or mag2 == 0:
        return 1.0

    similarity = dot_product / ((mag1**0.5) * (mag2**0.5))

    return 1.0 - similarity


class GraphConsistency(Consistency):
    """
    Calculates consistency for execution graph data using NetworkX GED
    or sequence-based dissimilarity.
    """

    def __init__(
        self,
        statistic: str = "average_pairwise_wl_distance",
        confidence_level: float = 95,
        sample_size: int = 10,
        N_nearest_neighbors: int = 100,
        N_bootstrap_samples: int = 2000,
    ):
        super().__init__(
            statistic=statistic,
            confidence_level=confidence_level,
            sample_size=sample_size,
            N_nearest_neighbors=N_nearest_neighbors,
            N_bootstrap_samples=N_bootstrap_samples,
        )

        if self.statistic == "average_pairwise_wl_distance":
            self.statistic_function = (
                self._calculate_average_pairwise_wl_distance_statistic
            )
        else:
            raise ValueError(
                f"Unknown statistic: {self.statistic}. Supported: 'average_pairwise_wl_distance'."
            )

    def _calculate_average_pairwise_wl_distance_statistic(
        self,
        original_graphs: np.ndarray,
        bootstrap_graph_samples: np.ndarray,
    ) -> np.ndarray:
        """
        Computes the average pairwise graph edit distance using networkx's
        optimize_graph_edit_distance for each bootstrap sample.
        """
        ged_dissimilarities = []
        for bs_graphs in bootstrap_graph_samples:
            current_sample = list(bs_graphs)

            if len(current_sample) < 2:
                ged_dissimilarities.append(0.0)
                continue

            pairwise_scores = []
            for i in range(len(current_sample)):
                for j in range(i + 1, len(current_sample)):
                    distance = wl_distance(
                        current_sample[i], current_sample[j], iterations=4
                    )
                    pairwise_scores.append(distance)

            ged_dissimilarities.append(
                np.mean(pairwise_scores) if pairwise_scores else 0.0
            )

        return np.array(ged_dissimilarities)

    def calculate_consistency(
        self,
        data: List[nx.Graph],
    ) -> ConsistencyResult:
        """
        Calculates the consistency score for a given list of NetworkX graphs.
        """
        if not data:
            return ConsistencyResult()

        if len(data) < self.sample_size:
            self.sample_size = len(data)
            if self.sample_size < 2:
                return ConsistencyResult()

        consistency_with_conf = self._calculate_consistency_with_confidence(sample=data)

        max_score = 1.0
        return self._format_consistency_result(
            consistency_with_conf, max_score, self.statistic
        )
