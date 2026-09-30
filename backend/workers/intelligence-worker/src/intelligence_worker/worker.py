#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from typing import Optional

from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseTriggerMessage

from intelligence_worker.wrapper.intelligence_wrapper import IntelligenceWrapper

logger = logging.getLogger(__name__)


class IntelligenceWorker(BaseWorker):
    """Worker responsible for executing intelligence catalog templates."""

    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        output_queue: Optional[list[str]] = None,
        feedback_queue: Optional[str] = None,
        message_limit: int = -1,
        max_inflight_messages: int = 1,
        periodic_trigger_interval_seconds: float = 600.0,
        debug: bool = False,
        catalog_root: str = ".",
        template_max_concurrency: int = 8,
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
        self.name = "IntelligenceWorker"
        self.input_message_class = BaseTriggerMessage
        self.wrapper = IntelligenceWrapper(
            catalog_root=catalog_root,
            db_handler=self.db_handler,
        )
        self.debug = debug
        self.template_max_concurrency = template_max_concurrency
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
                app_ids = sorted(self.wrapper.db_handler.get_all_application_ids())
                if not app_ids:
                    logger.info("Periodic self-trigger: no MAS application ids found.")
                    continue

                for app_id in app_ids:
                    trigger = BaseTriggerMessage(application_id=app_id)
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

    async def handle_message(self, msg: BaseTriggerMessage):
        if self.db_handler is None:
            logger.warning("Connection to database is missing. Dropping message.")
            return False

        results = await self.wrapper.generate_insights(
            application_id=msg.application_id,
            max_concurrency=self.template_max_concurrency,
        )
        logger.info(
            "Executed %d insight template queries for application_id=%s",
            len(results),
            msg.application_id,
        )
        return True
