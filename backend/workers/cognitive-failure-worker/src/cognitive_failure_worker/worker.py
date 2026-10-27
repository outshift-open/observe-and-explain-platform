#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import os
from typing import Optional

import yaml
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage

from cognitive_failure_worker.failures import select_failures
from cognitive_failure_worker.agent import ChatReply, ToolCall, investigate
from cognitive_failure_worker.detector import DetectorError
from cognitive_failure_worker.trace_file import sweep_stale

logger = logging.getLogger(__name__)

class CognitiveFailureWorker(BaseWorker):
    """Worker that detects cognitive failures in a session.

    Fetches the session's trajectory from the KG through the OXP API library, writes it to a
    temporary file (deleted afterwards) and lets an agent read it with tools, without access to the API
    or the graph, to find which of the configured failures (from the challenges taxonomy) it shows. The
    worker then writes a ``CognitiveFailureReport`` for each, attached to the session and to the call
    where it happened. Re-running a session overwrites the same detections. Which failures to look for is set in
    the config file; with none, the worker detects nothing.
    """

    def __init__(
        self,
        rabbit_url: str,
        input_queue: str,
        output_queue: Optional[list[str]] = None,
        feedback_queue=None,
        message_limit: int = -1,
        max_inflight_messages: int = 4,
        llm_api_key: Optional[str] = None,
        llm_model_name: Optional[str] = None,
        llm_base_model_url: Optional[str] = None,
        config_path: Optional[str] = None,
        debug: bool = False,
    ):
        super().__init__(
            rabbitmq_url=rabbit_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )
        self.name = "CognitiveFailureWorker"
        self.input_message_class = BaseQueueMessage
        self.debug = debug

        self.llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY", "")
        self.llm_model_name = llm_model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o")
        self.llm_base_model_url = llm_base_model_url or os.getenv("LLM_BASE_MODEL_URL_MCE", "https://api.openai.com/v1")

        self.failures = self._failures_from(config_path)
        if not self.failures:
            logger.warning("No cognitive failure is configured: the worker will not detect anything")
        self._client = None
        sweep_stale()  # trace files a killed process left behind

    @staticmethod
    def _failures_from(config_path: Optional[str]) -> list[dict]:
        """The failures listed under ``failures`` in the config file; none without a file or a list.

        Checked here, so a misspelt setting or failure code stops the worker at startup and not
        on every message.
        """
        if not config_path:
            return []
        with open(config_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        unknown = set(config) - {"failures"}
        if unknown:
            raise ValueError(f"Unknown setting(s) in {config_path}: {', '.join(sorted(unknown))}")
        codes = config.get("failures") or []
        return select_failures([codes] if isinstance(codes, str) else codes)

    def _get_kg(self):
        """The shared Neo4j connector (owned and closed by the base worker)."""
        from oxp.dependencies import get_neo4j_connector

        return get_neo4j_connector()

    def _chat(self, messages: list[dict], tools: list[dict], force_tool: str | None) -> ChatReply:
        """One chat completion from the judge model, with tools; ``force_tool`` makes it call that tool."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.llm_api_key, base_url=self.llm_base_model_url)
        options = {}
        if force_tool:
            options["tool_choice"] = {"type": "function", "function": {"name": force_tool}}
        response = self._client.chat.completions.create(
            model=self.llm_model_name, messages=messages, tools=tools, temperature=0, **options
        )
        message = response.choices[0].message
        usage = getattr(response, "usage", None)
        return ChatReply(
            content=message.content or "",
            tool_calls=[ToolCall(c.id, c.function.name, c.function.arguments) for c in message.tool_calls or []],
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )

    def _detect_and_write(self, kg, session_id: str) -> None:
        from oxp.client.failures import write_cognitive_failure_reports
        from oxp.client.dal import get_session_trajectory

        trajectory = get_session_trajectory(kg, session_id)
        if not trajectory["steps"]:
            logger.warning("Session %s has no trajectory steps: nothing to detect", session_id)
            return
        try:
            result = investigate(trajectory, self.failures, self._chat)
        except DetectorError as exc:
            logger.error("Cognitive failure detection failed for session %s: %s", session_id, exc)
            return
        written = write_cognitive_failure_reports(kg, session_id, [d.as_dict() for d in result.detections])
        logger.info(
            "Session %s: %d failure(s) detected, %d written | turns=%d tokens=%d",
            session_id,
            len(result.detections),
            written,
            result.turns,
            result.prompt_tokens + result.completion_tokens,
        )

    async def handle_message(self, msg: BaseQueueMessage):
        logger.info("CognitiveFailureWorker: checking session %s", msg.session_id)
        if self.failures:
            await asyncio.to_thread(self._detect_and_write, self._get_kg(), msg.session_id)

        self.output_messages = [
            BaseQueueMessage(
                job_id=msg.job_id,
                session_id=msg.session_id,
                workflow_id=msg.workflow_id,
                local_file=msg.local_file,
            )
        ]
        return True
