#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from typing import Any, Dict, List, Optional

import norm
from oxp.client.dal import ingest_normalized_kg as oxp_api_ingest_normalized_kg
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_connector
from worker_base import queue_message
from worker_base.base_worker import BaseWorker

from norm_worker.wrapper.norm_wrapper import NormWrapper

logger = logging.getLogger(__name__)


def on_trace_normalized(
    spans: List[Dict[str, Any]],
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> None:
    print(
        f"Normalized {len(spans)} spans into {len(nodes)} nodes and {len(edges)} edges"
    )
    for node in nodes:
        print(f"  node {node.get('node_type')}: {node.get('id')}")
    for edge in edges:
        print(
            f"  edge {edge.get('edge_type')}: "
            f"{edge.get('from_id')} -> {edge.get('to_id')}"
        )


class OXPApiNormDALAdapter:
    def __init__(self, connector: Connector):
        self._connector = connector

    def close(self):
        self._connector.close()

    def ingest_normalized_kg(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        run_id: str,
        override: bool,
        batch_size: int = 200,
    ) -> bool:
        return oxp_api_ingest_normalized_kg(
            db=self._connector,
            nodes=nodes,
            edges=edges,
            run_id=run_id,
            override=override,
            batch_size=batch_size,
        )


class NormWorker(BaseWorker):
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        output_queue: Optional[list[str]] = None,
        feedback_queue=None,
        message_limit=-1,
        max_inflight_messages: int = 32,
        debug: bool = False,
        override: bool = False,  # whether to override existing data in norm, used for testing and re-processing sessions
        kg_output: Optional[str] = None,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue,
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )
        self.name = "NormWorker"

        norm.configure(on_normalized=on_trace_normalized)

        self.input_message_class = queue_message.BaseQueueMessage
        self.debug = debug
        self.override = override
        self.kg_output = kg_output

        try:
            self.db_handler = OXPApiNormDALAdapter(get_neo4j_connector())
        except Exception as exc:
            logger.warning(
                "Failed to initialize API-managed Neo4j connector; DB operations disabled: %s",
                exc,
            )
            self.db_handler = None

    async def handle_message(self, msg: queue_message.BaseQueueMessage):
        return await asyncio.to_thread(self._process_session, msg)

    def _process_session(self, msg: queue_message.BaseQueueMessage):
        logger.info(f"Processing session_id: {msg.session_id}")

        if self.db_handler is None:
            logger.warning("Connection to database is missing. Dropping message.")
            return None

        wrapper = NormWrapper(
            db_handler=self.db_handler,
            debug=self.debug,
            override=self.override,
            kg_output=self.kg_output,
        )

        kg = wrapper.retrieve_and_normalize(msg.session_id)

        if kg is None:
            logger.error("Normalization failed for session_id=%s", msg.session_id)
            return None

        success = wrapper.ingest_to_neo4j(kg)
        if not success:
            logger.error("Neo4j push failed for session_id=%s", msg.session_id)
            return None

        logger.info(f"Completed processing for session_id: {msg.session_id}")

        return True
