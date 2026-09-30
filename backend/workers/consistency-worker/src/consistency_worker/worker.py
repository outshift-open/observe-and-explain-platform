#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import logging
from typing import Any, Dict, List, Optional

from oxp_ontology.models.nodes.consistency_report import ConsistencyReport
from pydantic import Field
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage, SessionDetail

from consistency_worker.wrapper.consistency_wrapper import ConsistencyWrapper

logger = logging.getLogger(__name__)


class ConsistencyInputMessage(BaseQueueMessage):
    """Input message that may carry pre-fetched sessions (Argo/grouping-worker mode)."""

    group_id: str = Field(alias="group_id")
    group_hash: str = Field(alias="group_hash", default="")
    sessions: List[Dict[str, Any]] = Field(alias="sessions", default=[])


class ConsistencyOutputMessage(BaseQueueMessage):
    group_id: str
    sessions: List[Dict[str, Any]] = []
    consistency: List[Dict[str, Any]] = []


class ConsistencyWorker(BaseWorker):
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        embedding_model: str,
        layers: Optional[Dict[str, Any]] = None,
        output_queue: Optional[List[str]] = None,
        feedback_queue: Optional[str] = None,
        message_limit: int = -1,
        debug: bool = False,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
        )
        self.name = "ConsistencyWorker"
        self.input_message_class = ConsistencyInputMessage
        self.embedding_model = embedding_model
        self.wrapper = ConsistencyWrapper(debug=debug, layers=layers)

    async def handle_message(self, msg: ConsistencyInputMessage):
        # Use inline sessions if provided (run-once mode), otherwise fetch from Neo4j
        if msg.sessions:
            group_data = msg.sessions
        else:
            if not self.embedding_model:
                logger.error("Embedding model not provided. Dropping message.")
                return False

            if self.db_handler is None:
                logger.warning("Connection to database is missing. Dropping message.")
                return False

            if not await self.db_handler.wait_for_hierarchical_grouping_unlock():
                logger.info(
                    "Hierarchical grouping lock active, skipping consistency for group %s.",
                    msg.group_id,
                )
                return False

            if not self.db_handler.analysis_pre_check(
                group_id=msg.group_id,
                report_type=ConsistencyReport.__name__,
                group_hash=msg.group_hash,
                session_id=msg.session_id,
            ):
                logger.debug("Analysis pre-check failed. Either group changed or report already exists.")
                return False

            group_data = self.db_handler.get_analysis_data_for_semantic_group(
                msg.group_id,
                msg.group_hash,
                self.embedding_model,
            )
            if not group_data:
                return False

            if msg.session_id:
                session_ids = [gd["session_id"] for gd in group_data]
                if msg.session_id not in session_ids:
                    return False

        analysis_data = [SessionDetail.model_validate(s) for s in group_data]
        consistency_report = self.wrapper.process_group(analysis_data)

        if len(consistency_report) == 0:
            logger.info("No consistency reports generated for the session group.")
            return True

        if self.db_handler is not None:
            links_created = self.wrapper.ingest_consistency(
                self.db_handler,
                consistency_report,
                msg.group_id,
                node_hash=msg.group_hash,
            )
            if not links_created:
                logger.info(
                    "Some consistency reports failed to attach to group %s. Continuing.",
                    msg.group_id,
                )

        self.output_messages = [
            ConsistencyOutputMessage(
                session_id=msg.session_id,
                group_id=msg.group_id,
                sessions=[s.model_dump() for s in analysis_data],
                consistency=[
                    {
                        "consistency_result": r.consistency_result.__dict__,
                        "session_ids": r.session_ids,
                        "layer": r.layer,
                        "metadata": r.metadata,
                    }
                    for r in consistency_report
                ],
            )
        ]
        return True
