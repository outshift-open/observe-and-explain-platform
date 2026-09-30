#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import contextvars
import json
import logging
import os
import uuid
from typing import Any, Callable

import aio_pika
from oxp.dependencies import get_neo4j_connector

from worker_base.dal_adapter import OXPApiDALAdapter
from worker_base.queue_message import BaseMessage, FeedbackMessage
from worker_base.utils import resolve_rabbitmq_url

logger = logging.getLogger(__name__)


class BaseWorker:
    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        output_queue: list[str] = [],
        feedback_queue: str | None = None,
        message_limit: int = -1,  # -1 for unlimited messages, otherwise the worker will stop after processing this many messages (useful for testing)
        max_inflight_messages: int = 1,
        output_message_ttl_seconds: float | None = None,
    ):
        self.rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.feedback_queue = feedback_queue
        self.message_limit = message_limit
        self.max_inflight_messages = max(1, max_inflight_messages)
        self.output_message_ttl_seconds = output_message_ttl_seconds
        self.input_message_class = BaseMessage
        self.channel = None
        self.name = "BaseWorker"  # this will be overridden by class implementation
        self.db_handler = None

        # Store output messages in task-local context so concurrent message processing
        # does not overwrite outputs from another in-flight message.
        self._output_messages_ctx = contextvars.ContextVar(f"{self.__class__.__name__}_output_messages", default=[])
        self._argo_output_emitter_ctx: contextvars.ContextVar[Callable[[Any], None] | None] = contextvars.ContextVar(
            f"{self.__class__.__name__}_argo_output_emitter", default=None
        )

        try:
            self.db_handler = OXPApiDALAdapter(get_neo4j_connector())
        except Exception as exc:
            logger.warning(
                "Failed to initialize API-managed Neo4j connector; DB operations disabled: %s",
                exc,
            )
            self.db_handler = None

        # This is where the subclass should put the output message
        # If left as is, it will just pass the input message through to the next queue(s)
        self.output_messages = []

    @property
    def output_messages(self):
        return self._output_messages_ctx.get()

    @output_messages.setter
    def output_messages(self, value):
        self._output_messages_ctx.set(value)

    def emit_output_message(self, message):
        emitter = self._argo_output_emitter_ctx.get()
        if emitter is not None:
            emitter(message)
            return

        output_messages = self.output_messages or []
        if not isinstance(output_messages, list):
            output_messages = [output_messages]
        output_messages.append(message)
        self.output_messages = output_messages

    async def run(
        self,
    ):
        logger.debug("%s started", self.name)
        await self.run_worker()

    @staticmethod
    def _load_argo_input(raw_input: str):
        if raw_input is None:
            raise ValueError("Argo input is required")

        stripped = raw_input.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            return json.loads(stripped)

        if os.path.exists(raw_input):
            with open(raw_input, "r", encoding="utf-8") as handle:
                return json.loads(handle.read())

        raise ValueError("Argo input must be JSON or a path to a JSON file")

    @staticmethod
    def _write_argo_output(output_path: str, payload):
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    @staticmethod
    def _serialize_output_message(message) -> dict:
        if hasattr(message, "model_dump"):
            serialized = message.model_dump(
                by_alias=True,
                exclude={"job_id", "local_file"},
                exclude_none=True,
            )
        elif isinstance(message, dict):
            serialized = dict(message)
            serialized.pop("job_id", None)
            serialized.pop("local_file", None)
        else:
            serialized = message
        return serialized

    async def run_argo_message(self, raw_input: str, output_path: str):
        raw_payload = self._load_argo_input(raw_input)

        # Support both single message (dict) and array of messages (list)
        is_batch = isinstance(raw_payload, list)
        input_payloads = raw_payload if is_batch else [raw_payload]

        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        total = len(input_payloads)

        if not is_batch:
            # Single message: accumulate and write at end (original behaviour)
            payload = self.input_message_class.model_validate(input_payloads[0])
            if not payload.workflow_id:
                payload.workflow_id = str(uuid.uuid4())
            self.output_messages = [payload]
            result = await self.handle_message(payload)
            if result is None:
                raise RuntimeError("Worker failed to process input message")
            if result is False:
                logger.info(
                    "Worker processed message but returned False, treating as successful processing with no output"
                )
                self.output_messages = []
            output_messages = self.output_messages or []
            if not isinstance(output_messages, list):
                output_messages = [output_messages]
            output_payload = [self._serialize_output_message(m) for m in output_messages]
            final_payload = output_payload[0] if len(output_payload) == 1 else output_payload
            self._write_argo_output(output_path, final_payload)
            return final_payload

        # Batch mode: stream output to file to avoid OOM on large arrays
        logger.info(
            "Batch mode: processing %d messages, streaming output to %s",
            total,
            output_path,
        )
        written = 0
        with open(output_path, "w", encoding="utf-8", buffering=1) as out_file:
            out_file.write("[\n")
            out_file.flush()

            def emit_streamed_output(message):
                nonlocal written
                serialized = self._serialize_output_message(message)
                if written > 0:
                    out_file.write(",\n")
                json.dump(serialized, out_file, indent=2)
                out_file.flush()
                written += 1

            for idx, raw_msg in enumerate(input_payloads):
                logger.info("Batch [%d/%d] start — validating message", idx + 1, total)
                payload = self.input_message_class.model_validate(raw_msg)
                if not payload.workflow_id:
                    payload.workflow_id = str(uuid.uuid4())
                logger.info(
                    "Batch [%d/%d] handling message (group_id=%s)",
                    idx + 1,
                    total,
                    getattr(payload, "group_id", "?"),
                )
                self.output_messages = [payload]
                emitter_token = self._argo_output_emitter_ctx.set(emit_streamed_output)
                try:
                    result = await self.handle_message(payload)
                except Exception as exc:
                    logger.exception(
                        "Batch [%d/%d] handle_message raised an exception, skipping: %s",
                        idx + 1,
                        total,
                        exc,
                    )
                    result = False
                    self.output_messages = []
                finally:
                    self._argo_output_emitter_ctx.reset(emitter_token)
                logger.info("Batch [%d/%d] handle_message returned: %s", idx + 1, total, result)
                if result is False:
                    logger.info("Batch [%d/%d] returned False, skipping output", idx + 1, total)
                    self.output_messages = []
                output_messages = self.output_messages or []
                if not isinstance(output_messages, list):
                    output_messages = [output_messages]
                logger.info(
                    "Batch [%d/%d] serializing %d output message(s)",
                    idx + 1,
                    total,
                    len(output_messages),
                )
                for message in output_messages:
                    serialized = self._serialize_output_message(message)
                    if written > 0:
                        out_file.write(",\n")
                    json.dump(serialized, out_file, indent=2)
                    written += 1
                out_file.flush()
                logger.info(
                    "Batch [%d/%d] done — %d total written so far",
                    idx + 1,
                    total,
                    written,
                )
            out_file.write("\n]")
            out_file.flush()

        logger.info("Batch complete: wrote %d output messages to %s", written, output_path)
        # Return a lightweight summary rather than loading the full file back into memory
        return {
            "batch": True,
            "total_input": total,
            "total_output": written,
            "output_path": output_path,
        }

    async def run_worker(self):
        connection = None
        inflight_tasks: set[asyncio.Task] = set()
        try:
            connection = await aio_pika.connect_robust(self.rabbitmq_url)
            self.channel = await connection.channel()
            await self.channel.set_qos(prefetch_count=self.max_inflight_messages)

            queue = await self.channel.declare_queue(self.input_queue, durable=True, auto_delete=False)
            scheduled = 0
            async with queue.iterator() as messages:
                async for message in messages:
                    if self.message_limit > 0 and scheduled >= self.message_limit:
                        logger.info(f"{self.name}: reached processing limit of {self.message_limit}. Stopping worker.")
                        break

                    if len(inflight_tasks) >= self.max_inflight_messages:
                        done, pending = await asyncio.wait(
                            inflight_tasks,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        inflight_tasks = set(pending)
                        for task in done:
                            if task.exception() is not None:
                                logger.exception(
                                    "%s: uncaught exception in worker task",
                                    self.name,
                                    exc_info=task.exception(),
                                )

                    inflight_tasks.add(asyncio.create_task(self._process_single_message(message)))
                    scheduled += 1

            if inflight_tasks:
                done, _ = await asyncio.wait(inflight_tasks)
                for task in done:
                    if task.exception() is not None:
                        logger.exception(
                            "%s: uncaught exception in worker task",
                            self.name,
                            exc_info=task.exception(),
                        )
        finally:
            if connection is not None and not connection.is_closed:
                await connection.close()
            self._close_db_handler()

    def _close_db_handler(self):
        if self.db_handler is None:
            return
        close_fn = getattr(self.db_handler, "close", None)
        if not callable(close_fn):
            return
        try:
            close_fn()
        except Exception:
            logger.exception("Failed to close DB handler for %s", self.name)

    async def _process_single_message(self, message):
        async with message.process():
            try:
                payload = self.input_message_class.from_body(message.body)
                self.output_messages = [payload]

                primary_id = (
                    getattr(payload, "session_id", None)
                    or getattr(payload, "application_id", None)
                    or getattr(payload, "group_id", None)
                )

                if not primary_id:
                    logger.error(
                        f"No identifier (session_id, application_id, or group_id) found in {type(payload).__name__}, skipping."
                    )
                    return

                workflow_id = payload.workflow_id
                if not workflow_id:
                    workflow_id = str(uuid.uuid4())
            except Exception as e:
                logger.exception(f"Error parsing message: {e}")
                # we can't even parse the message, so we don't have a session_id or workflow_id to send feedback about, but we can still log the error and skip the message
                return
            try:
                input = payload.dump_message()
                if self.feedback_queue:
                    feedback = FeedbackMessage(
                        session_id=primary_id,
                        input=input,
                        event="start",
                        workflow=self.name,
                        workflow_id=workflow_id,
                        queue_name=self.input_queue,
                    )
                    await feedback.write_message(self.channel, self.feedback_queue)

                res = await self.handle_message(payload)

                outcome = "complete"
                if res is None:
                    # error
                    outcome = "error"
                else:
                    if res:
                        await self.propagate_message()

                if self.feedback_queue:
                    feedback = FeedbackMessage(
                        session_id=primary_id,
                        event=outcome,
                        workflow=self.name,
                        workflow_id=workflow_id,
                    )
                    await feedback.write_message(self.channel, self.feedback_queue)

            except Exception as e:
                logger.exception(f"Error processing message: {e}")
                if self.feedback_queue:
                    feedback = FeedbackMessage(
                        session_id=primary_id,
                        event="error",
                        workflow=self.name,
                        workflow_id=(payload.workflow_id if "payload" in locals() else None),
                    )
                    await feedback.write_message(self.channel, self.feedback_queue)

    async def propagate_message(self):
        if self.output_queue:
            # check if output_messages is a list (in case a subclass forgot to put an array)
            if self.output_messages and not isinstance(self.output_messages, list):
                self.output_messages = [self.output_messages]
            for message in self.output_messages:
                await self.send_message_to_all(message)
        else:
            logger.info(f"{self.name} has no output queue defined, processing ends here.")

    async def send_message_to_all(self, message: BaseMessage):
        if self.channel:
            for q in self.output_queue:
                logger.info(f"Sending message to queue: {q}")
                await message.write_message(self.channel, q, ttl_seconds=self.output_message_ttl_seconds)

    # not used, but just in case someone wants to send a message to a specific queue from within the worker, they can use this method
    async def send_message_to_queue(self, queue_name: str, message: BaseMessage):
        if self.channel:
            logger.info("Sending message to queue: %s", queue_name)
            await message.write_message(self.channel, queue_name, ttl_seconds=self.output_message_ttl_seconds)

    # SUBCLASSES MUST OVERRIDE THIS METHOD TO DEFINE THEIR OWN LOGIC
    async def handle_message(self, msg: BaseMessage):
        raise NotImplementedError("Subclasses must implement handle_message method")
