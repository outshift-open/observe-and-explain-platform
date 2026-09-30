#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import List
import networkx as nx
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer

from .base import AnomalyDetector
from .utils import AnomalyDetectionResult
from ..utils import setup_logger

logger = setup_logger(__name__)


class GraphAnomalyDetector(AnomalyDetector):
    """
    Anomaly detector for graph-structured data.
    """

    def __init__(self, model_name=None, max_path_length=10, **kwargs):
        super().__init__(model_name, **kwargs)
        self.max_path_length = max_path_length

    def _extract_path_ngrams(self, G: nx.Graph) -> str:
        """
        Decomposes a NetworkX graph into a 'document' of paths.
        Each path is represented as a string of agent_ids joined by '__'.
        """
        if G is None or G.number_of_nodes() == 0:
            return ""

        node_to_agent = {
            n: str(data.get("agent_id", "unknown")).replace(" ", "_")
            for n, data in G.nodes(data=True)
        }

        paths = []

        def find_paths(current_node, current_path_labels):
            paths.append("__".join(current_path_labels))

            if len(current_path_labels) < self.max_path_length:
                neighbors = (
                    G.successors(current_node)
                    if G.is_directed()
                    else G.neighbors(current_node)
                )
                for neighbor in neighbors:
                    find_paths(
                        neighbor, current_path_labels + [node_to_agent[neighbor]]
                    )

        for node in G.nodes():
            find_paths(node, [node_to_agent[node]])

        return " ".join(paths)

    def detect_outliers(self, graph_data: List[nx.Graph]) -> AnomalyDetectionResult:
        """
        Detects anomalies in graph data.

        Args:
            graph_data (List[nx.Graph]): The input list of graph data.

        Returns:
            AnomalyDetectionResult: An object containing the detection results.
        """
        if not graph_data:
            logger.warning("No graph data provided. Returning empty result.")
            return AnomalyDetectionResult()

        graph_documents = [self._extract_path_ngrams(g) for g in graph_data]
        vectorizer = CountVectorizer(token_pattern=r"(?u)\b\w[\w-]*\b")

        try:
            feature_matrix = vectorizer.fit_transform(graph_documents).toarray()
        except ValueError:
            return AnomalyDetectionResult(
                inliers_indices=list(range(len(graph_data))), inliers_values=graph_data
            )

        if feature_matrix.shape[0] < 2:
            return AnomalyDetectionResult(
                inliers_indices=[0] if graph_data else [],
                inliers_values=graph_data if graph_data else [],
            )

        if np.all(feature_matrix == feature_matrix[0, :]):
            y_pred = np.ones(feature_matrix.shape[0])
        else:
            try:
                y_pred = self.model.fit_predict(feature_matrix)
            except ValueError as e:
                if "The covariance matrix of the support data is equal to 0" in str(e):
                    y_pred = np.ones(feature_matrix.shape[0])
                else:
                    raise

        inliers_indices = [i for i, pred in enumerate(y_pred) if pred == 1]
        outliers_indices = [i for i, pred in enumerate(y_pred) if pred == -1]

        return AnomalyDetectionResult(
            inliers_indices=inliers_indices,
            inliers_values=[graph_data[i] for i in inliers_indices],
            outliers_indices=outliers_indices,
            outliers_values=[graph_data[i] for i in outliers_indices],
        )
