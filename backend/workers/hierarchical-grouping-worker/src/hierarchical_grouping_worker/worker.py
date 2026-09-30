#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from typing import Any, Dict, List, Optional

from oxp.client.dal import (
    acquire_hierarchical_grouping_lock as oxp_api_acquire_hierarchical_grouping_lock,
)
from oxp.client.dal import (
    get_all_application_ids as oxp_api_get_all_application_ids,
)
from oxp.client.dal import (
    get_all_session_input_embeddings as oxp_api_get_all_session_input_embeddings,
)
from oxp.client.dal import (
    get_semantic_group_hierarchy as oxp_api_get_semantic_group_hierarchy,
)
from oxp.client.dal import (
    get_semantic_groups_needing_analysis as oxp_api_get_semantic_groups_needing_analysis,
)
from oxp.client.dal import (
    ingest_semantic_groups as oxp_api_ingest_semantic_groups,
)
from oxp.client.dal import (
    release_hierarchical_grouping_lock as oxp_api_release_hierarchical_grouping_lock,
)
from oxp.client.dal import (
    update_semantic_group_names_and_summaries as oxp_api_update_semantic_group_names_and_summaries,
)
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_connector
from worker_base import queue_message
from worker_base.base_worker import BaseWorker

from hierarchical_grouping_worker.wrapper.hierarchical_grouping_wrapper import (
    HierarchicalGroupingWrapper,
)

logger = logging.getLogger(__name__)


class OXPApiHierarchicalGroupingDALAdapter:
    def __init__(self, connector: Connector):
        self._connector = connector

    def close(self):
        self._connector.close()

    def acquire_hierarchical_grouping_lock(
        self,
        owner: str,
        ttl_seconds: int = 300,
    ) -> bool:
        return oxp_api_acquire_hierarchical_grouping_lock(
            db=self._connector,
            owner=owner,
            ttl_seconds=ttl_seconds,
        )

    def release_hierarchical_grouping_lock(self, owner: str) -> bool:
        return oxp_api_release_hierarchical_grouping_lock(
            db=self._connector,
            owner=owner,
        )

    def get_all_session_input_embeddings(
        self,
        application_id: str,
        embedding_model: str,
    ) -> List[Dict[str, Any]]:
        return oxp_api_get_all_session_input_embeddings(
            db=self._connector,
            application_id=application_id,
            embedding_model=embedding_model,
        )

    def get_semantic_group_hierarchy(
        self,
        embedding_model: str,
        application_id: str,
    ) -> List[Dict[str, Any]]:
        return oxp_api_get_semantic_group_hierarchy(
            db=self._connector,
            embedding_model=embedding_model,
            application_id=application_id,
        )

    def ingest_semantic_groups(
        self,
        group_hierarchy: List[Dict[str, Any]],
        delta: Dict[str, List[str]],
        application_id: str,
    ) -> None:
        oxp_api_ingest_semantic_groups(
            db=self._connector,
            group_hierarchy=group_hierarchy,
            delta=delta,
            application_id=application_id,
        )

    def update_semantic_group_names_and_summaries(
        self,
        group_hierarchy: List[Dict[str, Any]],
        update_ids: List[str],
    ) -> None:
        if not update_ids:
            return
        group_nodes = [group for group in group_hierarchy if group.get("id") in update_ids]
        if not group_nodes:
            return
        oxp_api_update_semantic_group_names_and_summaries(
            db=self._connector,
            group_nodes=group_nodes,
        )

    def get_semantic_groups_needing_analysis(
        self,
        embedding_model: str,
    ) -> List[tuple[str, str]]:
        return oxp_api_get_semantic_groups_needing_analysis(
            db=self._connector,
            embedding_model=embedding_model,
        )

    def get_all_application_ids(self) -> List[str]:
        return oxp_api_get_all_application_ids(db=self._connector)


class HierarchicalGroupingWorker(BaseWorker):
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        llm_base_url: str,
        llm_model_name: str,
        llm_api_key: str,
        embedding_model: str,
        max_neighbors: int,
        min_samples: int = 20,
        max_distance: float = 0.15,
        debug: bool = False,
        output_queue: Optional[list[str]] = None,
        feedback_queue: Optional[str] = None,
        message_limit: int = -1,
        max_inflight_messages: int = 1,
        periodic_trigger_interval_seconds: float = 60.0,
    ):
        self._periodic_trigger_interval_seconds = periodic_trigger_interval_seconds
        output_message_ttl_seconds = periodic_trigger_interval_seconds * 1.5

        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
            output_message_ttl_seconds=output_message_ttl_seconds,
        )
        self.name = "hierarchical_grouping_worker"
        self.input_message_class = queue_message.BaseTriggerMessage

        if not embedding_model:
            raise ValueError("Missing embedding model name.")

        try:
            db_handler = OXPApiHierarchicalGroupingDALAdapter(get_neo4j_connector())
        except Exception as exc:
            logger.warning(
                "Failed to initialize API-managed Neo4j connector; DB operations disabled: %s",
                exc,
            )
            db_handler = None
        self.db_handler = db_handler

        self.grouper = HierarchicalGroupingWrapper(
            db_handler=db_handler,
            min_samples=min_samples,
            max_neighbors=max_neighbors,
            max_distance=max_distance,
            llm_base_url=llm_base_url,
            llm_model_name=llm_model_name,
            llm_api_key=llm_api_key,
            embedding_model=embedding_model,
            debug=False,
        )
        self.debug = debug
        self._periodic_task: Optional[asyncio.Task] = None

    async def run(self):
        logger.info("Worker started")
        self._periodic_task = asyncio.create_task(self._periodic_self_trigger())
        try:
            await self.run_worker()
        finally:
            if self._periodic_task and not self._periodic_task.done():
                self._periodic_task.cancel()

    async def _periodic_self_trigger(self):
        while self.channel is None:
            await asyncio.sleep(0.5)
        while True:
            try:
                await asyncio.sleep(self._periodic_trigger_interval_seconds)
                app_ids = sorted(self.grouper.db_handler.get_all_application_ids())
                if not app_ids:
                    logger.info("Periodic self-trigger: no MAS application ids found.")
                    continue
                for app_id in app_ids:
                    trigger = queue_message.BaseTriggerMessage(application_id=app_id)
                    await trigger.write_message(
                        self.channel,
                        self.input_queue,
                        ttl_seconds=self.output_message_ttl_seconds,
                    )
                    logger.info(
                        "Periodic self-trigger published for application_id=%s",
                        app_id,
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Periodic self-trigger iteration failed")

    async def handle_message(self, msg: queue_message.BaseTriggerMessage):
        logger.info(f"Received message in {self.name}: {msg.__dict__}")

        groups_to_analyze = await self.grouper.compute_semantic_groups(application_id=msg.application_id)

        groups_needing_analysis = self.grouper.db_handler.get_semantic_groups_needing_analysis(
            embedding_model=self.grouper.embedding_model
        )

        logger.info(
            f"Found {len(groups_to_analyze)} newly created/updated groups "
            f"and {len(groups_needing_analysis)} groups needing analysis"
        )

        seen = set()
        all_groups = []

        for group_id, group_hash in groups_to_analyze:
            key = (group_id, group_hash)
            if key not in seen:
                seen.add(key)
                all_groups.append((group_id, group_hash))

        for group_id, group_hash in groups_needing_analysis:
            key = (group_id, group_hash)
            if key not in seen:
                seen.add(key)
                all_groups.append((group_id, group_hash))

        self.output_messages = []
        for group_id, group_hash in all_groups:
            self.output_messages.append(
                queue_message.SessionGroupMessage(
                    job_id=msg.job_id,
                    workflow_id=msg.workflow_id,
                    local_file=msg.local_file,
                    session_id="",
                    group_id=group_id,
                    group_hash=group_hash,
                )
            )

        return True
