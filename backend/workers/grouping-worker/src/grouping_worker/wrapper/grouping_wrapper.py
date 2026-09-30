#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any, Dict, List, Protocol, Tuple

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class GroupInfo(BaseModel):
    group_id: str
    node_hash: str


class GroupingDALHandler(Protocol):
    async def wait_for_hierarchical_grouping_unlock(self) -> bool: ...

    def get_analysis_data_for_semantic_group(
        self,
        group_id: str,
        group_hash: str,
        embedding_model: str,
    ) -> List[Dict[str, Any]]: ...

    def get_session_group(
        self,
        session_id: str,
        embedding_model: str,
        max_distance: float,
    ) -> Tuple[str, str]: ...

    def attach_session_to_group(
        self,
        session_id: str,
        group_id: str,
        node_hash: str,
    ) -> bool: ...


class GroupingWrapper:
    def __init__(
        self,
        db_handler: GroupingDALHandler,
        embedding_model: str,
        max_neighbors: int = 10,
        max_distance: float = 0.3,
        debug: bool = False,
    ):
        self.db_handler = db_handler
        self.embedding_model = embedding_model
        self.max_neighbors = max_neighbors
        self.max_distance = max_distance
        self.debug = debug

    async def wait_for_hierarchical_grouping_unlock(self) -> bool:
        return await self.db_handler.wait_for_hierarchical_grouping_unlock()

    def get_analysis_data_for_semantic_group(
        self,
        group_id: str,
        group_hash: str,
        embedding_model: str,
    ) -> List[Dict[str, Any]]:
        return self.db_handler.get_analysis_data_for_semantic_group(
            group_id=group_id,
            group_hash=group_hash,
            embedding_model=embedding_model,
        )

    def process_session(self, session_id: str) -> GroupInfo:
        group_info = GroupInfo(group_id="", node_hash="")

        if not session_id:
            logger.warning("Empty session ID provided to grouping wrapper. Skipping.")
            return group_info

        group_id, node_hash = self.db_handler.get_session_group(
            session_id=session_id,
            embedding_model=self.embedding_model,
            max_distance=self.max_distance,
        )
        if not group_id:
            logger.debug(f"Could not match session {session_id} to a group.")
            return group_info

        # Ensure node_hash is a string; None causes the Cypher WHERE clause to fail
        node_hash = node_hash or ""

        attached = self.db_handler.attach_session_to_group(
            session_id=session_id,
            group_id=group_id,
            node_hash=node_hash,
        )
        if not attached:
            return group_info

        return GroupInfo(group_id=group_id, node_hash=node_hash)
