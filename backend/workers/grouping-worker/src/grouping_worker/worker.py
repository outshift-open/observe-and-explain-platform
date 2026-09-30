#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from oxp.client.dal import (
    attach_session_to_group as oxp_api_attach_session_to_group,
)
from oxp.client.dal import (
    get_analysis_data_for_semantic_group as oxp_api_get_analysis_data_for_semantic_group,
)
from oxp.client.dal import get_session_group as oxp_api_get_session_group
from oxp.client.dal import (
    wait_for_hierarchical_grouping_unlock as oxp_api_wait_for_hierarchical_grouping_unlock,
)
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_connector
from worker_base import queue_message
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import SessionGroupMessage

from grouping_worker.wrapper.grouping_wrapper import GroupingWrapper

logger = logging.getLogger(__name__)


class OXPApiGroupingDALAdapter:
    def __init__(self, connector: Connector):
        self._connector = connector

    def close(self):
        self._connector.close()

    async def wait_for_hierarchical_grouping_unlock(self) -> bool:
        return await oxp_api_wait_for_hierarchical_grouping_unlock(db=self._connector)

    def get_analysis_data_for_semantic_group(
        self,
        group_id: str,
        group_hash: str,
        embedding_model: str,
    ) -> List[Dict[str, Any]]:
        return oxp_api_get_analysis_data_for_semantic_group(
            db=self._connector,
            group_id=group_id,
            group_hash=group_hash,
            embedding_model=embedding_model,
        )

    def get_session_group(
        self,
        session_id: str,
        embedding_model: str,
        max_distance: float,
    ) -> Tuple[str, str]:
        return oxp_api_get_session_group(
            db=self._connector,
            session_id=session_id,
            embedding_model=embedding_model,
            max_distance=max_distance,
        )

    def attach_session_to_group(
        self,
        session_id: str,
        group_id: str,
        node_hash: str,
    ) -> bool:
        return oxp_api_attach_session_to_group(
            db=self._connector,
            session_id=session_id,
            group_id=group_id,
            node_hash=node_hash,
        )


class GroupingWorker(BaseWorker):
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        embedding_model: str,
        max_neighbors: int = 10,
        max_distance: float = 0.3,
        debug: bool = False,
        output_queue: Optional[List[str]] = None,
        feedback_queue: Optional[str] = None,
        message_limit: int = -1,
        max_inflight_messages: int = 16,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )
        self.name = "grouping_worker"
        self.input_message_class = queue_message.SessionDetailMessage

        if not embedding_model:
            raise ValueError("Missing embedding model name.")

        try:
            self.db_handler = OXPApiGroupingDALAdapter(get_neo4j_connector())
        except Exception as exc:
            logger.warning(
                "Failed to initialize API-managed Neo4j connector; DB operations disabled: %s",
                exc,
            )
            self.db_handler = None

        self.grouper = GroupingWrapper(
            db_handler=self.db_handler,
            embedding_model=embedding_model,
            max_neighbors=max_neighbors,
            max_distance=max_distance,
            debug=debug,
        )
        self.embedding_model = embedding_model
        self.debug = debug

    async def handle_message(self, msg: queue_message.SessionDetailMessage):
        logger.info(f"{self.name}: received message for session {msg.session_id}")

        if self.db_handler is None:
            logger.warning("Connection to database is missing. Dropping message.")
            return False

        if not await self.grouper.wait_for_hierarchical_grouping_unlock():
            logger.info("Hierarchical grouping lock is active, skipping quick grouping for now.")
            return False

        group_info = await asyncio.to_thread(self.grouper.process_session, msg.session_id)

        if not group_info.group_id:
            return False

        logger.info(f"Grouping done: attached {msg.session_id} to {group_info.group_id}")

        # Fetch all session data for the group so downstream workers can run in run-once mode
        sessions = await asyncio.to_thread(
            self.grouper.get_analysis_data_for_semantic_group,
            group_info.group_id,
            group_info.node_hash,
            self.embedding_model,
        )

        self.output_messages = [
            SessionGroupMessage(
                session_id=msg.session_id,
                job_id=msg.job_id,
                workflow_id=msg.workflow_id,
                local_file=msg.local_file,
                group_id=group_info.group_id,
                group_hash=group_info.node_hash,
                sessions=sessions,
            )
        ]
        return True
