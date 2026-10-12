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

    Reads a session's normalized trajectory (Transition/State chain and the
    LLM, tool and agent calls it represents) from the KG through the OXP API
    library's DAL, invokes the Stateful Evals library on it, and writes the
    results back onto the Transition nodes. The KG connection is the shared
    Neo4j connector every worker uses; no OTel store is involved.
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
        self.push_context = os.getenv("PUSH_TRANSITION_CONTEXT", "true").strip().lower() not in ("false", "0", "no")

    def _get_kg(self):
        """The shared Neo4j connector (owned and closed by the base worker)."""
        from oxp.dependencies import get_neo4j_connector

        return get_neo4j_connector()

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

    @staticmethod
    def _fetch_trajectory(kg, session_id: str) -> dict:
        from oxp.client.dal import get_session_trajectory

        trajectory = get_session_trajectory(kg, session_id)
        logger.info("Read %d trajectory steps for session %s", len(trajectory["steps"]), session_id)
        return trajectory

    async def handle_message(self, msg: BaseQueueMessage):
        session_id = msg.session_id
        logger.info(f"StatefulEvalWorker: evaluating session {session_id}")

        kg = self._get_kg()
        processor = self._build_processor()
        try:
            trajectory = await asyncio.to_thread(self._fetch_trajectory, kg, session_id)
            result = await asyncio.to_thread(processor.evaluate_trajectory, trajectory)
        finally:
            processor.close()

        if result.error:
            logger.error(f"StatefulEvalWorker: session {session_id} error: {result.error}")

        if self.push_metrics and not result.error:
            await asyncio.to_thread(self._push_metrics_to_kg, kg, result)
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

    def _push_metrics_to_kg(self, kg, result) -> None:
        """Write step metrics, trajectory context and the session score to the KG."""
        from oxp.client.dal import write_transition_context
        from oxp.interfaces.models import MetricResult
        from oxp.providers import OXPMetricsProvider

        provider = OXPMetricsProvider(db=kg)

        grouped: dict = {}
        for smr in result.span_metric_results:
            if not smr.transition_id:
                logger.warning("Skipping %s: no transition id on span %s", smr.metric_name, smr.span_id)
                continue
            grouped.setdefault(smr.transition_id, []).append(smr)

        for transition_id, smrs in grouped.items():
            ok = provider.save_transition_metrics(
                result.session_id,
                transition_id,
                [
                    MetricResult(
                        metric_id=smr.metric_name,
                        resource_id=transition_id,
                        provider="stateful_evals",
                        value=smr.score,
                        reasoning=smr.reasoning,
                        metadata={"metric_id": None, "source": "StatefulEval"},
                    )
                    for smr in smrs
                ],
            )
            if ok:
                logger.info("Wrote %d metrics for transition %s", len(smrs), transition_id)
            else:
                logger.error("Could not write all metrics for transition %s", transition_id)

        if self.push_context:
            for transition_id, context in (getattr(result, "transition_contexts", None) or {}).items():
                if not write_transition_context(kg, result.session_id, transition_id, context):
                    logger.error("Could not write context for transition %s", transition_id)

        if result.trajectory_score is not None:
            ok = provider.save_metrics(
                [
                    MetricResult(
                        metric_id="TrajectoryScore",
                        resource_id=result.session_id,
                        provider="stateful_evals",
                        value=result.trajectory_score,
                        reasoning=result.trajectory_reasoning,
                        metadata={"metric_id": None, "source": "StatefulEval"},
                    )
                ]
            )
            if ok:
                logger.info("Wrote TrajectoryScore=%s for session %s", result.trajectory_score, result.session_id)
            else:
                logger.error("Could not write TrajectoryScore for session %s", result.session_id)
