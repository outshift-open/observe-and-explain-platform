#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import logging
from typing import Optional

from worker_base.base_worker import BaseWorker
from worker_base.queue_message import SessionDetailMessage

from mce_worker.wrapper.mce_wrapper import MCEWrapper

logger = logging.getLogger(__name__)


class MCEWorker(BaseWorker):
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        output_queue: Optional[list[str]] = None,
        feedback_queue=None,
        message_limit: int = -1,
        max_inflight_messages: int = 1,
        config_path: Optional[str] = None,
        neo4j_uri: Optional[str] = None,
        neo4j_user: Optional[str] = None,
        neo4j_password: Optional[str] = None,
        neo4j_database: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        llm_model_name: Optional[str] = None,
        llm_base_model_url: Optional[str] = None,
        metrics: Optional[list[str]] = None,
        debug: bool = False,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )
        self.name = "MCEWorker"
        self.input_message_class = SessionDetailMessage

        self.mce = MCEWrapper(
            config_path=config_path,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            neo4j_database=neo4j_database,
            llm_api_key=llm_api_key,
            llm_model_name=llm_model_name,
            llm_base_model_url=llm_base_model_url,
            metrics=metrics,
            debug=debug,
        )

    async def handle_message(self, msg: SessionDetailMessage):
        await self.mce.process_mce_session(msg.session_id, msg.local_file)
        self.output_messages = [msg]
        return True
