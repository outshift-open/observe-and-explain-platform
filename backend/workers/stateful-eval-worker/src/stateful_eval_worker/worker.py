#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import asyncio
import logging
import os
from typing import Optional

import yaml
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage

logger = logging.getLogger(__name__)


_SPAN_EVALUATION_FIELDS = (
    "evaluation_model",
    "evaluation_prompt_tokens",
    "evaluation_completion_tokens",
    "evaluation_total_tokens",
    "evaluation_cost_usd",
)


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

        self.trajectory_metrics = self._trajectory_metrics_from(config_path)

        self.push_metrics = os.getenv("PUSH_METRICS", "true").strip().lower() not in ("false", "0", "no")
        self.push_context = os.getenv("PUSH_TRANSITION_CONTEXT", "true").strip().lower() not in ("false", "0", "no")

    @staticmethod
    def _trajectory_metrics_from(config_path: Optional[str]) -> Optional[list[str]]:
        """The ``trajectory_metrics`` of the config file: ``all`` or a list of names or codes.

        With no file, or an empty list, no trajectory metric runs. The file is checked
        here, so a misspelt key or metric stops the worker at startup and not on every message.
        """
        if not config_path:
            return None
        with open(config_path, encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
        unknown = set(config) - {"trajectory_metrics"}
        if unknown:
            raise ValueError(f"Unknown setting(s) in {config_path}: {', '.join(sorted(unknown))}")

        selectors = config.get("trajectory_metrics") or []
        if isinstance(selectors, str):
            selectors = [selectors]
        if not selectors:
            return None
        from stateful_evals_be.evaluation.trajectory_context_metrics.trajectory_metrics import (
            resolve_trajectory_metric_codes,
        )

        resolve_trajectory_metric_codes(selectors)
        return list(selectors)

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
            options=TemporalMetricOptions(sampling=sampling_cfg, trajectory_metrics=self.trajectory_metrics),
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

    def _session_evaluation_fields(self, result) -> dict:
        """Total evaluation usage (all phases) and estimated cost of the session."""
        fields: dict = {"evaluation_model": self.llm_model_name}
        usage = result.token_usage
        if usage.total_tokens or usage.prompt_tokens or usage.completion_tokens:
            fields["evaluation_prompt_tokens"] = usage.prompt_tokens
            fields["evaluation_completion_tokens"] = usage.completion_tokens
            fields["evaluation_total_tokens"] = usage.total_tokens
            fields["evaluation_cost_usd"] = result.cost_estimate.estimated_cost_usd
        return fields

    def _trajectory_metric_results(self, result) -> list:
        """The session's trajectory metrics as ``MetricResult``s measuring the session.

        A metric that was not applicable or could not be judged has no score and is not written.
        """
        from oxp.interfaces.models import MetricResult
        from stateful_evals_be.evaluation.cost_estimator import estimate_usage_cost_usd

        results = []
        skipped = 0
        for item in result.trajectory_metrics:
            if item.get("score") is None:
                skipped += 1
                continue
            usage = (item.get("metadata") or {}).get("usage") or {}
            metadata: dict = {"evaluation_model": self.llm_model_name}
            if usage.get("total_tokens"):
                metadata["evaluation_prompt_tokens"] = usage["prompt_tokens"]
                metadata["evaluation_completion_tokens"] = usage["completion_tokens"]
                metadata["evaluation_total_tokens"] = usage["total_tokens"]
                metadata["evaluation_cost_usd"] = estimate_usage_cost_usd(
                    usage["prompt_tokens"], usage["completion_tokens"], self.llm_model_name
                )
            results.append(
                MetricResult(
                    metric_id="".join(item["high_level_metric"].split()),
                    resource_id=result.session_id,
                    provider="StatefulEvals",
                    value=item["score"],
                    reasoning=item.get("reasoning"),
                    metadata=metadata,
                )
            )
        if skipped:
            logger.info("Skipping %d trajectory metrics without a score for session %s", skipped, result.session_id)
        return results

    def _push_metrics_to_kg(self, kg, result) -> None:
        """Write step metrics, trajectory context and the session score to the KG."""
        from oxp.client.dal import write_transition_context
        from oxp.interfaces.models import MetricResult
        from oxp.providers import OXPMetricsProvider

        provider = OXPMetricsProvider(db=kg)

        # A step's span id is the id of its call node, which the metrics measure.
        grouped: dict = {}
        for smr in result.span_metric_results:
            if not smr.span_id:
                logger.warning("Skipping %s: no call id on its span result", smr.metric_name)
                continue
            grouped.setdefault(smr.span_id, []).append(smr)

        for call_id, smrs in grouped.items():
            # Evaluation usage/cost keys are only sent when measured; they become the
            # evaluation fields of the MetricResult.
            ok = provider.save_call_metrics(
                result.session_id,
                call_id,
                [
                    MetricResult(
                        metric_id=smr.metric_name,
                        resource_id=call_id,
                        provider="StatefulEvals",
                        value=smr.score,
                        reasoning=smr.reasoning,
                        metadata={
                            field: getattr(smr, field)
                            for field in _SPAN_EVALUATION_FIELDS
                            if getattr(smr, field, None) is not None
                        },
                    )
                    for smr in smrs
                ],
            )
            if ok:
                logger.info("Wrote %d metrics for call %s", len(smrs), call_id)
            else:
                logger.error("Could not write all metrics for call %s", call_id)

        if self.push_context:
            for transition_id, context in (getattr(result, "transition_contexts", None) or {}).items():
                if not write_transition_context(kg, result.session_id, transition_id, context):
                    logger.error("Could not write context for transition %s", transition_id)

        trajectory_metrics = self._trajectory_metric_results(result)
        if trajectory_metrics:
            ok = provider.save_metrics(trajectory_metrics)
            if ok:
                logger.info("Wrote %d trajectory metrics for session %s", len(trajectory_metrics), result.session_id)
            else:
                logger.error("Could not write all trajectory metrics for session %s", result.session_id)

        if result.trajectory_score is not None:
            ok = provider.save_metrics(
                [
                    MetricResult(
                        metric_id="TrajectoryScore",
                        resource_id=result.session_id,
                        provider="StatefulEvals",
                        value=result.trajectory_score,
                        reasoning=result.trajectory_reasoning,
                        metadata=self._session_evaluation_fields(result),
                    )
                ]
            )
            if ok:
                logger.info("Wrote TrajectoryScore=%s for session %s", result.trajectory_score, result.session_id)
            else:
                logger.error("Could not write TrajectoryScore for session %s", result.session_id)
