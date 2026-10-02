#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import os
from typing import Optional

from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage

logger = logging.getLogger(__name__)


class StatefulEvalWorker(BaseWorker):
    """Worker that runs temporal metric evaluation directly in-process.

    Fetches spans, invokes the Stateful Evals library, and persists results.
    Span fetching and metric writes both bypass the REST API layer and go
    directly to the KG via the oxp-api library.
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
        self.name = "StatefulEvalWorker"
        self.input_message_class = BaseQueueMessage
        self.debug = debug

        self.llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY", "")
        self.llm_model_name = llm_model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o")
        self.llm_base_model_url = llm_base_model_url or os.getenv("LLM_BASE_MODEL_URL_MCE", "https://api.openai.com/v1")

        # Adaptive span sampling — opt-in via env vars
        self.sampling_strategy = os.getenv("SAMPLING_STRATEGY", "none").strip().lower()
        self.sampling_early_rate = float(os.getenv("SAMPLING_EARLY_RATE", "0.25"))
        self.sampling_mid_rate = float(os.getenv("SAMPLING_MID_RATE", "0.60"))

        self.push_metrics = os.getenv("PUSH_METRICS", "true").strip().lower() not in ("false", "0", "no")

        # Lazy-initialised shared LocalClient (one Neo4j driver pool per worker)
        self._oxp_client = None

    def _get_oxp_client(self):
        if self._oxp_client is None:
            from oxp.client.local import LocalClient

            neo4j = None
            if self.push_metrics:
                # Same shared connector BaseWorker and every other worker use, so
                # metric writes reuse its driver and its NEO4J_URI/host:port handling.
                from oxp.dependencies import get_neo4j_connector

                neo4j = get_neo4j_connector()
            self._oxp_client = LocalClient.from_settings(persist_metrics=self.push_metrics, neo4j=neo4j)
        return self._oxp_client

    def _close_db_handler(self):
        try:
            if self._oxp_client is not None:
                self._oxp_client.close()
                self._oxp_client = None
        finally:
            super()._close_db_handler()

    def _build_processor(self):
        """Create a fresh TemporalMetricsProcessor for one session evaluation.

        A new instance per message is safe and sidesteps the thread-safety
        issue with _last_cross_span_usage / _last_final_outcome_usage being
        mutated on the shared instance during concurrent evaluations.
        The per-session overhead is negligible because the metric catalog is
        cached after the first warm-up.

        """
        from metrics_computation_engine.models.requests import LLMJudgeConfig
        from stateful_evals_be import TemporalMetricsProcessor
        from stateful_evals_be.models.requests import SamplingConfig, TemporalMetricOptions

        llm_config = LLMJudgeConfig(
            LLM_MODEL_NAME=self.llm_model_name,
            LLM_BASE_MODEL_URL=self.llm_base_model_url,
            LLM_API_KEY=self.llm_api_key,
        )

        sampling_cfg = None
        if self.sampling_strategy == "tail_weighted":
            sampling_cfg = SamplingConfig(
                strategy="tail_weighted",
                early_rate=self.sampling_early_rate,
                mid_rate=self.sampling_mid_rate,
            )

        return TemporalMetricsProcessor(
            llm_config=llm_config,
            options=TemporalMetricOptions(sampling=sampling_cfg),
        )

    def _fetch_spans(self, session_id: str):
        from stateful_evals_be.integrations.oxp import fetch_session_spans

        spans = fetch_session_spans(self._get_oxp_client(), session_id)
        logger.info("Fetched %d spans for session %s (in-process)", len(spans), session_id)
        return spans

    async def handle_message(self, msg: BaseQueueMessage):
        session_id = msg.session_id
        logger.info(f"StatefulEvalWorker: evaluating session {session_id}")

        spans = await asyncio.to_thread(self._fetch_spans, session_id)
        processor = self._build_processor()
        try:
            result = await asyncio.to_thread(processor.evaluate_spans, spans, session_id=session_id)
        finally:
            processor.close()

        if result.error:
            logger.error(f"StatefulEvalWorker: session {session_id} error: {result.error}")

        if self.push_metrics and not result.error:
            await asyncio.to_thread(self._push_metrics_to_kg, result)
        elif self.push_metrics and result.error:
            logger.warning(f"StatefulEvalWorker: skipping KG write for session {session_id} due to eval error")

        self.output_messages = [
            BaseQueueMessage(
                job_id=msg.job_id,
                session_id=msg.session_id,
                workflow_id=msg.workflow_id,
                local_file=msg.local_file,
            )
        ]
        return True

    def _push_metrics_to_kg(self, result) -> None:
        """Write span and session-level metrics directly to the KG via the oxp-api lib."""
        client = self._get_oxp_client()

        if result.span_metric_results:
            grouped: dict = {}
            for smr in result.span_metric_results:
                key = smr.span_id or f"idx-{smr.span_index}"
                grouped.setdefault(key, []).append(smr)

            for span_id, smrs in grouped.items():
                metrics_payload = [
                    {
                        "name": smr.metric_name,
                        "value": smr.score,
                        "provider": "stateful_evals",
                        "metric_id": None,
                        "source": "StatefulEval",
                        "reasoning": smr.reasoning,
                    }
                    for smr in smrs
                ]
                resp = client.write_span_metrics(result.session_id, span_id, metrics_payload)
                errs = resp.get("errors", [])
                if errs:
                    logger.error("write_span_metrics errors for span %s: %s", span_id, errs)
                else:
                    logger.info("Wrote %d span metrics for span %s", resp.get("written", 0), span_id)

        if result.trajectory_score is not None:
            resp = client.write_session_metrics(
                result.session_id,
                [
                    {
                        "name": "trajectory_score",
                        "value": result.trajectory_score,
                        "provider": "stateful_evals",
                        "metric_id": None,
                        "source": "StatefulEval",
                        "reasoning": result.trajectory_reasoning,
                    }
                ],
            )
            errs = resp.get("errors", [])
            if errs:
                logger.error("write_session_metrics errors for session %s: %s", result.session_id, errs)
            else:
                logger.info(
                    "Wrote trajectory_score=%s for session %s",
                    result.trajectory_score,
                    result.session_id,
                )
