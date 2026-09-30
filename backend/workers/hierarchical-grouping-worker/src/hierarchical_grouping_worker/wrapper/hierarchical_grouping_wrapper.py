#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import logging
import uuid
from typing import Any, Dict, List, Protocol

import numpy as np
from dem.grouping import Hierarchy, SemanticGrouper
from dem.llm import LLM

logger = logging.getLogger(__name__)


class HierarchicalGroupingDALHandler(Protocol):
    def close(self) -> None: ...

    def acquire_hierarchical_grouping_lock(
        self,
        owner: str,
        ttl_seconds: int = 300,
    ) -> bool: ...

    def release_hierarchical_grouping_lock(self, owner: str) -> bool: ...

    def get_all_session_input_embeddings(
        self,
        application_id: str,
        embedding_model: str,
    ) -> List[Dict[str, Any]]: ...

    def get_semantic_group_hierarchy(
        self,
        embedding_model: str,
        application_id: str,
    ) -> List[Dict[str, Any]]: ...

    def ingest_semantic_groups(
        self,
        group_hierarchy: List[Dict[str, Any]],
        delta: Dict[str, List[str]],
        application_id: str,
    ) -> None: ...

    def update_semantic_group_names_and_summaries(
        self,
        group_hierarchy: List[Dict[str, Any]],
        update_ids: List[str],
    ) -> None: ...

    def get_semantic_groups_needing_analysis(
        self,
        embedding_model: str,
    ) -> List[tuple[str, str]]: ...

    def get_all_application_ids(self) -> List[str]: ...


class HierarchicalGroupingWrapper:
    def __init__(
        self,
        db_handler: HierarchicalGroupingDALHandler,
        llm_base_url: str,
        llm_model_name: str,
        llm_api_key: str,
        embedding_model: str,
        max_neighbors: int,
        min_samples: int = 20,
        llm_max_input_queries: int = 10,
        max_distance: float = 0.02,
        debug: bool = False,
    ):
        self.db_handler = db_handler

        self.llm = (
            LLM(
                llm_base_url=llm_base_url,
                llm_model_name=llm_model_name,
                llm_api_key=llm_api_key,
            )
            if llm_api_key
            else None
        )
        self.min_samples = min_samples
        self.llm_max_input_queries = llm_max_input_queries
        self.max_neighbors = max_neighbors
        self.max_distance = max_distance
        self.embedding_model = embedding_model
        self.debug = debug

    def close(self):
        if getattr(self, "db_handler", None) is not None:
            self.db_handler.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    async def compute_semantic_groups(self, application_id: str) -> List[tuple[str, str]]:
        lock_owner = f"hierarchical_grouping:{uuid.uuid4()}"
        lock_acquired = self.db_handler.acquire_hierarchical_grouping_lock(owner=lock_owner)
        if not lock_acquired:
            logger.warning("Another hierarchical grouping run is in progress, skipping this cycle.")
            return []

        queries = {}
        hierarchy = None
        delta = {}
        try:
            input_data = self.db_handler.get_all_session_input_embeddings(
                application_id=application_id,
                embedding_model=self.embedding_model,
            )

            if len(input_data) < self.min_samples:
                logger.warning(
                    f"Only {len(input_data)} sessions found in knowledge graph. At least {self.min_samples} required to compute hierarchical grouping."
                )
                return []

            embeddings = {}
            for data_row in input_data:
                queries[data_row["session_id"]] = data_row["input_query"]
                embeddings[data_row["session_id"]] = np.array(data_row["input_embedding"])

            semantic_grouper = SemanticGrouper(max_radius=self.max_distance)

            logger.info("Retrieving current semantic hierarchy")
            previous_hierarchy_raw = self.db_handler.get_semantic_group_hierarchy(
                embedding_model=self.embedding_model, application_id=application_id
            )
            previous_hierarchy = Hierarchy.from_list(previous_hierarchy_raw)

            logger.info("Computing semantic hierarchy")
            hierarchy, delta = semantic_grouper.compute_semantic_hierarchy(
                embeddings=embeddings,
                previous_hierarchy=previous_hierarchy,
            )

            if not hierarchy:
                return []

            for _, node in hierarchy.nodes.items():
                node.embedding_model = self.embedding_model

            if delta:
                additions = len(delta.get("add", []))
                deletions = len(delta.get("remove", []))
                updates = len(delta.get("update", []))
                if additions == 0 and deletions == 0 and updates == 0:
                    logger.info("No updates to current semantic group hierarchy.")
                else:
                    logger.info(
                        f"Updating {len(hierarchy)} semantic groups in knowledge graph: "
                        f"{additions} additions - "
                        f"{deletions} deletions - "
                        f"{updates} updates"
                    )

            self.db_handler.ingest_semantic_groups(
                group_hierarchy=hierarchy.to_list(),
                delta=delta,
                application_id=application_id,
            )
        finally:
            self.db_handler.release_hierarchical_grouping_lock(owner=lock_owner)

        if not hierarchy:
            return []

        if queries:
            updated_names_ids = await hierarchy.add_missing_group_names(
                input_queries=queries,
                llm=self.llm,
            )
            self.db_handler.update_semantic_group_names_and_summaries(
                group_hierarchy=hierarchy.to_list(),
                update_ids=updated_names_ids,
            )

        output_messages: list[tuple[str, str]] = []
        if delta:
            to_analyze_ids = []
            to_analyze_ids.extend(delta.get("add", []))
            to_analyze_ids.extend(delta.get("update", []))

            for group_id in to_analyze_ids:
                group = hierarchy.nodes.get(group_id)
                if group is None or not group.is_leaf:
                    continue
                group_hash = group.node_hash or ""
                output_messages.append((group_id, group_hash))

        return output_messages
