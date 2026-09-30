#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from typing import Any, Dict, List, Optional

from oxp.client.dal import get_state_content as oxp_api_get_state_content
from oxp.client.dal import ingest_embeddings as oxp_api_ingest_embeddings
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_connector
from worker_base import queue_message
from worker_base.base_worker import BaseWorker

from embedding_worker.wrapper import embedding_wrapper

logger = logging.getLogger(__name__)


class OXPApiEmbeddingDALAdapter:
    def __init__(self, connector: Connector):
        self._connector = connector

    def close(self):
        self._connector.close()

    def get_state_content(self, session_id: str) -> List[Dict[str, Any]]:
        return oxp_api_get_state_content(
            db=self._connector,
            filters_eq={"sessionId": session_id},
            filters_neq={"content": ""},
        )

    def ingest_embeddings(self, embeddings: List[Dict[str, Any]]) -> None:
        oxp_api_ingest_embeddings(
            db=self._connector,
            embeddings=embeddings,
        )


class EmbeddingWorker(BaseWorker):
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        output_queue: Optional[list[str]] = None,
        feedback_queue=None,
        message_limit=-1,
        max_inflight_messages: int = 16,
        debug: bool = False,
        embedder: Optional[str] = None,
        model: Optional[str] = None,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue,
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )
        self.name = "EmbeddingWorker"

        self.input_message_class = queue_message.BaseQueueMessage
        self.debug = debug

        try:
            self.db_handler = OXPApiEmbeddingDALAdapter(get_neo4j_connector())
        except Exception as exc:
            logger.warning(
                "Failed to initialize API-managed Neo4j connector; DB operations disabled: %s",
                exc,
            )
            self.db_handler = None

        # Initialize the embedding wrapper with the provided configuration
        self.embedder = embedding_wrapper.EmbeddingWrapper(
            args=None,
            db_handler=self.db_handler,
            debug=debug,
            embedder=embedder,
            model=model,
        )

    async def handle_message(self, msg: queue_message.BaseQueueMessage):
        logger.info(f"Processing session_id: {msg.session_id}")

        if self.db_handler is None:
            logger.warning("Connection to database is missing. Dropping message.")
            return False

        try:
            await asyncio.to_thread(self.embedder.process_session, msg.session_id)
            logger.info(f"Successfully embedded session_id: {msg.session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to embed session_id: {msg.session_id}: {e}")
            return None
