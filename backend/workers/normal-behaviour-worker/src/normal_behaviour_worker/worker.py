#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from oxp_ontology.models.nodes.normal_behaviour_report import NormalBehaviourReport
from pydantic import Field
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage, SessionDetail

from normal_behaviour_worker.wrapper.normal_behaviour_wrapper import (
    NormalBehaviourWrapper,
)

logger = logging.getLogger(__name__)


class NormalBehaviourInputMessage(BaseQueueMessage):
    """Extended input message that may carry pre-fetched sessions (run-once mode)."""

    group_id: str = Field(alias="group_id")
    group_hash: str = Field(alias="group_hash", default="")
    sessions: List[Dict[str, Any]] = Field(alias="sessions", default=[])


class NormalBehaviourOutputMessage(BaseQueueMessage):
    group_id: str
    sessions: List[Dict[str, Any]] = []
    normal_behaviour: List[Dict[str, Any]] = []


class NormalBehaviourWorker(BaseWorker):
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
        self.name = "NormalBehaviourWorker"
        self.input_message_class = NormalBehaviourInputMessage
        self.embedding_model = embedding_model
        self.wrapper = NormalBehaviourWrapper(debug=debug, layers=layers)

    async def handle_message(self, msg: NormalBehaviourInputMessage):
        if not self.embedding_model:
            logger.error("Embedding model not provided. Dropping message.")
            return False

        # Use inline sessions if provided (run-once mode), otherwise fetch from Neo4j
        if msg.sessions:
            group_data = msg.sessions
        else:
            if self.db_handler is None:
                logger.warning("Connection to database is missing. Dropping message.")
                return False

            if not self.db_handler.analysis_pre_check(
                group_id=msg.group_id,
                report_type=NormalBehaviourReport.__name__,
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
        normal_behaviour_report = self.wrapper.process_group(analysis_data)

        if len(normal_behaviour_report) == 0:
            logger.info("No normal behaviour reports generated for the session group.")
            return True

        if self.db_handler is not None:
            links_created = self._ingest_reports(normal_behaviour_report, msg.group_id, msg.group_hash)
            if not links_created:
                logger.info(f"Some normal behaviour reports failed to attach to group {msg.group_id}. Continuing.")

        self.output_messages = [
            NormalBehaviourOutputMessage(
                session_id=msg.session_id,
                group_id=msg.group_id,
                sessions=[s.model_dump() for s in analysis_data],
                normal_behaviour=[
                    {
                        "normal_behaviour": r.normal_behaviour.__dict__,
                        "session_ids": r.session_ids,
                        "layer": r.layer,
                        "metadata": r.metadata,
                    }
                    for r in normal_behaviour_report
                ],
            )
        ]
        return True

    def _ingest_reports(self, reports, group_id: str, group_hash: str) -> bool:
        all_ok = True
        for report in reports:
            metadata = report.metadata or {}
            raw_result = report.normal_behaviour.__dict__
            report_id = hashlib.sha256(
                (str(group_id) + str(report.layer) + str(metadata.get("metric", ""))).encode()
            ).hexdigest()
            representative_sample = report.normal_behaviour.representative_sample
            representative_processed_sample = getattr(report.normal_behaviour, "representative_processed_sample", None)
            node = NormalBehaviourReport(
                id=report_id,
                dataType=report.layer,
                rawResult=json.dumps(raw_result),
                centroid=json.dumps(report.normal_behaviour.centroid),
                representativeSample=json.dumps(representative_sample) if representative_sample is not None else "",
                representativeProcessedSample=representative_processed_sample or "",
            )
            if not self.db_handler.ingest_normal_behaviour_report(
                group_id=group_id,
                group_hash=group_hash,
                normal_behaviour_report=node,
                source=report,
            ):
                all_ok = False
        return all_ok
