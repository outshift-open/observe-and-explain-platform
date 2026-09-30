#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import hashlib
import random
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
import numpy as np
from sklearn.metrics.pairwise import cosine_distances

from ..llm import LLM, LLM_GENERATION_ERROR
from ..utils import setup_logger

logger = setup_logger(__name__)


class SemanticGroup(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    group_name: str = ""
    group_summary: str = ""
    session_ids: List[str] = Field(default_factory=list)
    n_sessions: int = 0
    medioid_session_id: str = ""
    children_nodes: List[str] = Field(default_factory=list)
    split_distance: float = 0.0
    embedding_model: str = ""
    node_hash: str = ""

    @property
    def is_leaf(self) -> bool:
        return len(self.children_nodes) == 0

    def apply_metadata(self, source: SemanticGroup):
        """Transfers name and summary from another group."""
        self.group_name = source.group_name
        self.group_summary = source.group_summary


class Hierarchy(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    nodes: Dict[str, SemanticGroup]
    _session_cache: Dict[str, Set[str]] = {}  # Cache node ID -> member session IDs

    @classmethod
    def from_list(self, data: List[Dict[str, Any]]) -> Hierarchy:
        return self(nodes={item["id"]: SemanticGroup(**item) for item in data})

    def to_list(self) -> List[Dict[str, Any]]:
        """Exports the hierarchy back to a list of dicts."""
        return [node.model_dump(by_alias=True) for node in self.nodes.values()]

    def __len__(self) -> int:
        """Retrieve total number of nodes in hierarchy."""
        return len(self.nodes)

    def __bool__(self) -> bool:
        """
        Returns True if nodes is non-empty, False otherwise.
        """
        return bool(self.nodes)

    def get_all_sessions(self, node_id: str) -> Set[str]:
        """Recursively retrieves all session IDs for a node and its descendants."""
        if node_id in self._session_cache:
            return self._session_cache[node_id]

        total_sessions: Set[str] = set()
        stack = [node_id]
        visited = set()

        while stack:
            curr_id = stack.pop()
            if curr_id in visited:
                logger.warning("Loop detected in hierarchy.")
                continue
            visited.add(curr_id)

            # If a sub-node is already cached, we can stop going deeper for this branch
            if curr_id in self._session_cache:
                total_sessions.update(self._session_cache[curr_id])
                continue

            node = self.nodes.get(curr_id)
            if node:
                # Add sessions directly belonging to this node
                if node.session_ids:
                    total_sessions.update(node.session_ids)

                # Add children to the stack to explore them
                if node.children_nodes:
                    stack.extend(node.children_nodes)

        # Cache the result for the requested node_id
        self._session_cache[node_id] = total_sessions
        return total_sessions

    def get_all_descendant_ids(self, node_id: str) -> Set[str]:
        """Helper to find every node ID beneath the given node."""
        descendants: Set[str] = set()

        node = self.nodes.get(node_id)
        if not node or not node.children_nodes:
            return descendants

        stack = list(node.children_nodes)

        while stack:
            curr_id = stack.pop()
            if curr_id not in descendants:
                descendants.add(curr_id)
                curr_node = self.nodes.get(curr_id)
                if curr_node and curr_node.children_nodes:
                    stack.extend(curr_node.children_nodes)

        return descendants

    def collapse_node(self, node_id: str):
        """
        Collapses a branch into a single leaf node.
        The target node inherits all session_ids from its subtree,
        and all descendant nodes are deleted.
        """
        if node_id not in self.nodes:
            return

        target_node = self.nodes[node_id]
        if target_node.is_leaf:
            return

        all_sessions = self.get_all_sessions(node_id)
        descendant_ids = self.get_all_descendant_ids(node_id)

        target_node.session_ids = list(all_sessions)
        target_node.n_sessions = len(all_sessions)
        target_node.children_nodes = []

        for d_id in descendant_ids:
            self.nodes.pop(d_id, None)
            self._session_cache.pop(d_id, None)

        self._session_cache.pop(node_id, None)

    def _rename_node_and_propagate(self, old_id: str, new_id: str):
        """
        Renames a node ID and updates all internal hierarchy references
        to ensure the tree remains intact.
        """
        if old_id not in self.nodes:
            return

        if new_id in self.nodes and new_id != old_id:
            logger.warning(f"Collision: {new_id} already exists. Skipping ID merge.")
            return

        # Update the node object and the main dictionary
        node = self.nodes.pop(old_id)
        node.id = new_id
        self.nodes[new_id] = node

        # Update any parent that points to the old_id
        for potential_parent in self.nodes.values():
            if old_id in potential_parent.children_nodes:
                potential_parent.children_nodes = [
                    new_id if child_id == old_id else child_id
                    for child_id in potential_parent.children_nodes
                ]

        # Update the session cache
        if old_id in self._session_cache:
            self._session_cache[new_id] = self._session_cache.pop(old_id)

    def merge_ids_from_previous(
        self,
        previous_hierarchy: Hierarchy,
        embeddings: Dict[str, np.ndarray],
        jaccard_threshold: float = 0.8,
        embedding_threshold: float = 0.2,
    ) -> Dict[str, List[str]]:
        """
        Matches nodes in this hierarchy to a previous one, propagates metadata,
        and renames the current node IDs to match the previous ones.
        """
        delta = {"add": [], "update": [], "remove": []}

        if not previous_hierarchy or not previous_hierarchy.nodes:
            delta["add"] = list(self.nodes.keys())
            return delta

        # Ensures embeddings are arrays
        embeddings_map = {}
        for key, value in embeddings.items():
            if isinstance(value, np.ndarray):
                embeddings_map[key] = value
            elif isinstance(value, list):
                embeddings_map[key] = np.array(value)
            else:
                raise TypeError(
                    f"Value for key '{key}' must be a list or numpy array, but got {type(value)}"
                )

        matched_previous_ids = set()
        ids_needing_update = set()
        ids_added = set()
        no_op_ids = set()

        used_previous_ids: Set[str] = set()
        current_ids = list(self.nodes.keys())

        for cid in current_ids:
            current_node = self.nodes.get(cid)
            if not current_node:
                continue

            current_sessions = set(self.get_all_sessions(current_node.id))
            if not current_sessions:
                continue

            best_match: Optional[SemanticGroup] = None
            max_jaccard = -1.0

            # 1. Try Jaccard Matching
            for prev_node in previous_hierarchy.nodes.values():
                if prev_node.id in used_previous_ids:
                    continue

                prev_sessions = set(previous_hierarchy.get_all_sessions(prev_node.id))
                intersection = len(current_sessions.intersection(prev_sessions))
                union = len(current_sessions.union(prev_sessions))
                jaccard = intersection / union if union > 0 else 0

                if jaccard == 1.0:
                    best_match = prev_node
                    max_jaccard = 1.0
                    break
                if jaccard > max_jaccard:
                    max_jaccard = jaccard
                    best_match = prev_node

            # 2. Medioid Embedding Fallback (if Jaccard fails)
            if (
                not best_match or max_jaccard < jaccard_threshold
            ) and current_node.medioid_session_id in embeddings_map:
                current_vec = embeddings_map[current_node.medioid_session_id]
                min_dist = float("inf")

                for prev_node in previous_hierarchy.nodes.values():
                    if prev_node.id in used_previous_ids:
                        continue

                    if prev_node.medioid_session_id in embeddings_map:
                        prev_vec = embeddings_map[prev_node.medioid_session_id]
                        dist = cosine_distances(
                            current_vec.reshape(1, -1), prev_vec.reshape(1, -1)
                        ).item()

                        if dist < min_dist and dist <= embedding_threshold:
                            min_dist = dist
                            best_match = prev_node

            # 3. Apply Match and Propagate ID Change
            if best_match:
                structure_changed = (
                    set(current_node.session_ids) != set(best_match.session_ids)
                    or current_node.medioid_session_id != best_match.medioid_session_id
                    or current_node.n_sessions != best_match.n_sessions
                    or set(current_node.children_nodes)
                    != set(best_match.children_nodes)
                )

                used_previous_ids.add(best_match.id)

                is_exact_sessions = max_jaccard == 1.0

                old_id = current_node.id
                new_id = best_match.id

                logger.debug(f"Merging: {old_id} -> {new_id}")

                current_node.apply_metadata(best_match)
                if old_id != new_id:
                    self._rename_node_and_propagate(old_id, new_id)

                matched_previous_ids.add(new_id)
                direct_sessions_changed = set(current_node.session_ids) != set(
                    best_match.session_ids
                )
                if is_exact_sessions and not direct_sessions_changed:
                    no_op_ids.add(new_id)
                elif structure_changed or direct_sessions_changed:
                    ids_needing_update.add(new_id)
            else:
                ids_added.add(current_node.id)

        for node_id, _ in self.nodes.items():
            if node_id in ids_added:
                delta["add"].append(node_id)
            elif node_id in ids_needing_update:
                delta["update"].append(node_id)

        delta["remove"] = list(
            set(previous_hierarchy.nodes.keys()) - matched_previous_ids
        )

        return delta

    async def add_missing_group_names(
        self,
        input_queries: Dict[str, str],
        llm: LLM,
        max_input_queries: int = 10,
    ) -> List[str]:
        if not llm:
            logger.warning("LLM not provided, skipping group name generation.")
            return []

        nodes_to_process = []
        nodes_updated = []
        for node_id, group in self.nodes.items():
            # Only process leaf nodes for name generation
            if not group.is_leaf:
                continue
            if (
                not group.group_name
                or not group.group_summary
                or group.group_name == LLM_GENERATION_ERROR
            ):
                # Use direct session_ids; get_all_sessions() would be redundant for leaf nodes
                if not group.session_ids:
                    continue

                ns = min(len(group.session_ids), max_input_queries)
                queries = [
                    input_queries[s] for s in random.sample(group.session_ids, ns)
                ]

                # Handle single-query edge case immediately to save LLM costs
                if (
                    len(queries) > 1
                    and queries[0] == queries[-1]
                    and all(q == queries[0] for q in queries)
                ):
                    group.group_name = queries[0]
                    group.group_summary = queries[0]
                    nodes_updated.append(node_id)
                elif len(queries) > 0:
                    nodes_to_process.append((node_id, queries))

        # Send the batch to LLM class
        if nodes_to_process:
            logger.info(
                f"Generating semantic group names: processing {len(nodes_to_process)} nodes in parallel."
            )
            results = await llm.process_nodes_batch(nodes_to_process)

            # Apply results back to the hierarchy
            for node_id, (name, summary) in results.items():
                self.nodes[node_id].group_name = name
                self.nodes[node_id].group_summary = summary
                nodes_updated.append(node_id)

        return nodes_updated

    def update_content_hashes(self):
        """
        Update node hashes from children sessions
        """
        for node_id, node in self.nodes.items():
            raw_session_ids = self.get_all_sessions(node_id)
            session_set = sorted({s for s in raw_session_ids if s})
            node.node_hash = hashlib.sha256(",".join(session_set).encode()).hexdigest()
