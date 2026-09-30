#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import uuid
from typing import Any, Dict, List, Sequence, Tuple, Union

from hdbscan import HDBSCAN
import numpy as np
from sklearn.metrics.pairwise import cosine_distances

from .utils import Hierarchy, SemanticGroup
from ..utils import setup_logger

logger = setup_logger(__name__)

EmbeddingLike = List[float]


class SemanticGrouper:
    """
    Manages the process of clustering embeddings into semantic groups, merging
    results with previous clusters, and assigning human-readable names and summaries.
    """

    def __init__(
        self,
        max_radius: float = 0.15,
        min_cluster_size: int = 2,
    ):
        """
        Initializes the SemanticGrouper with database client, LLM, and clustering parameters.

        Args:
            max_radius (float): Maximum cosine distance for a point to be in a cluster.
            min_cluster_size (int): Minimum number of points for a valid cluster.
        """
        self.max_radius = max_radius
        self.min_cluster_size = min_cluster_size

        self.clusterer = HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric="precomputed",
            prediction_data=True,
            cluster_selection_epsilon=self.max_radius,
        )

        logger.debug(f"Initialized semantic grouper with : {self.__dict__}")

    def get_cluster_hierarchy(
        self,
        embeddings: Union[Dict[str, Any], Sequence[Any]],
    ) -> Hierarchy:
        """
        Returns the structure of the HDBSCAN condensed tree as a Hierarchy of SemanticGroups.
        Collapses nodes based on max_radius and calculates medioids for all resulting groups.
        """
        # Embeddings pre-processing
        if isinstance(embeddings, (list, tuple, np.ndarray)):
            embeddings_dict = {str(i): emb for i, emb in enumerate(embeddings)}
        elif isinstance(embeddings, dict):
            embeddings_dict = embeddings
        else:
            raise TypeError("embeddings must be a Dict or Sequence of embeddings.")
        if not embeddings_dict:
            return Hierarchy(nodes={})

        session_ids = list(embeddings_dict.keys())
        embeddings_array = np.asarray(list(embeddings_dict.values()), dtype=float)

        # Run clustering
        distance_matrix = np.round(cosine_distances(embeddings_array), decimals=10)
        self.clusterer.fit(distance_matrix)

        raw_tree = self.clusterer.condensed_tree_._raw_tree

        # Initialize Hierarchy and Node Mapping
        hierarchy = Hierarchy(nodes={})
        node_to_group_id = {}

        def get_or_create_node(hdbscan_id: int, is_internal: bool = True) -> str:
            if hdbscan_id not in node_to_group_id:
                prefix = "sg_internal" if is_internal else "sg_leaf"
                node_to_group_id[hdbscan_id] = (
                    f"{prefix}_{hdbscan_id}_{str(uuid.uuid4())[:8]}"
                )

                # Create the Pydantic object
                new_node = SemanticGroup(id=node_to_group_id[hdbscan_id])
                hierarchy.nodes[new_node.id] = new_node

            return node_to_group_id[hdbscan_id]

        # Build the Tree Structure
        for row in raw_tree:
            parent_id = int(row["parent"])
            child_id = int(row["child"])
            child_size = int(row["child_size"])
            lambda_val = float(row["lambda_val"])
            split_dist = 1.0 / lambda_val if lambda_val > 0 else 1.0

            p_label = get_or_create_node(parent_id, is_internal=True)
            parent_node = hierarchy.nodes[p_label]
            parent_node.split_distance = split_dist

            if child_size > 1:
                # Child is a sub-cluster (internal node)
                c_label = get_or_create_node(child_id, is_internal=True)
                parent_node.children_nodes.append(c_label)
                hierarchy.nodes[c_label].n_sessions = child_size
            else:
                # Child is a single session (leaf)
                parent_node.session_ids.append(session_ids[child_id])

        # Deduplicate children_nodes (HDBSCAN emits multiple rows per parent)
        for node in hierarchy.nodes.values():
            if node.children_nodes:
                seen = []
                for cid in node.children_nodes:
                    if cid not in seen:
                        seen.append(cid)
                node.children_nodes = seen

        # Fix n_sessions
        for node in hierarchy.nodes.values():
            node.n_sessions = len(hierarchy.get_all_sessions(node.id))

        # Collapse Nodes based on max_radius
        for node_id in list(hierarchy.nodes):
            node = hierarchy.nodes.get(node_id)
            if node and node.children_nodes and node.split_distance < self.max_radius:
                hierarchy.collapse_node(node_id)
                node.split_distance = self.max_radius

        # Calculate medioids for all remaining nodes
        for node in hierarchy.nodes.values():
            current_sessions = hierarchy.get_all_sessions(node.id)

            if current_sessions:
                cluster_embs = [
                    embeddings_dict[sid]
                    for sid in current_sessions
                    if sid in embeddings_dict
                ]
                if not cluster_embs:
                    continue

                cluster_embs_arr = np.array(cluster_embs)
                centroid = np.mean(cluster_embs_arr, axis=0)

                # Find the session closest to the centroid
                dists = cosine_distances(
                    cluster_embs_arr, centroid.reshape(1, -1)
                ).flatten()
                closest_idx = np.argmin(dists)

                node.medioid_session_id = list(current_sessions)[closest_idx]

        return hierarchy

    def compute_semantic_hierarchy(
        self,
        embeddings: Dict[str, EmbeddingLike],
        previous_hierarchy: Hierarchy = None,
    ) -> Tuple[Hierarchy, Dict[str, List[str]]]:
        """
        Extracts semantic groups (clusters) from an application. This method either fetches
        embeddings from the database or uses provided embeddings, then performs clustering,
        merges group IDs from previous clustering results, assigns names, and formats the results.

        Args:
            queries (Dict[str, str]): A dictionary of session IDs to associated
                input query.
            embeddings (Dict[str, EmbeddingLike]): A dictionary of session IDs
                to embedding vectors.
            previous_hierarchy (Hierarchy): A semantic hierarchy object as reference

        Returns:
            Hierarchy: A semantic hierarchy tree object.
        """

        if not embeddings:
            logger.info(
                "No embeddings provided with the given parameters. Returning empty result."
            )
            return Hierarchy(nodes={}), {}

        # Perform clustering on the provided embeddings
        hierarchy = self.get_cluster_hierarchy(embeddings=embeddings)
        hierarchy.update_content_hashes()

        # Merge cluster IDs to propagate IDs/names/summaries
        delta = hierarchy.merge_ids_from_previous(
            previous_hierarchy=previous_hierarchy,
            embeddings=embeddings,
        )

        return hierarchy, delta
