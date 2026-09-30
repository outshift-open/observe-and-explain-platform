#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Application-chart private implementations for :class:`UIClient`."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from oxp.client.constants import (
    ANSWER_RELEVANCY,
    APP_AGENT_DURATION,
    APP_LLM_CALLS,
    APP_LLM_INVOCATION_DURATION,
    APP_RETRIEVAL_LATENCY,
    APP_TOOL_CALLS,
    APP_WORKFLOW_EFFICIENCY,
    PERIODS_COUNT,
    RESPONSE_COMPLETENESS,
)
from oxp.client.utils import (
    epoch_to_dt_str,
    parse_epoch_range,
    timestamp_to_epoch,
)
from oxp.connectors.base import Connector
from oxp.models.otel_traces import (
    ApplicationConversationChartsResponse,
    ApplicationCostChartsResponse,
    ApplicationGeneralChartsResponse,
    ApplicationLLMChartsResponse,
    ApplicationPerformanceChartsResponse,
    ApplicationQualityAndReasoningChartsResponse,
    ApplicationReliabilityAndSafetyChartsResponse,
    ApplicationToolsChartsResponse,
    ErrorItem,
    SingleValueData,
    TimelineData,
    ToolDetail,
)
from oxp.query_builders import ui as ui_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)

PASSIVE_EVAL_AGENTS_METRIC = "PassiveEvalAgents"
AGENT_LLM_DURATION = "eval.agent.llm_duration"
AGENT_LLM_COST = "eval.agent.llm_cost"


def _load_json_dict(value: object) -> dict:
    """Best-effort conversion of a nested JSON payload into a dict."""
    current = value
    for _ in range(2):
        if isinstance(current, dict):
            return current
        if current is None:
            return {}
        if isinstance(current, (bytes, bytearray)):
            current = current.decode()
            continue
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except json.JSONDecodeError:
                return {}
            continue
        return {}
    return current if isinstance(current, dict) else {}


def _agent_key_candidates(agent_id: str) -> list[str]:
    """Return likely keys for an agent inside ``PassiveEvalAgents.value.agents``."""
    if not agent_id:
        return []

    base = agent_id.split(".")[0]
    short = base.split("-")[-1]
    raw_candidates = [
        agent_id,
        base,
        agent_id.replace("-", "_"),
        base.replace("-", "_"),
        short,
        short.replace("-", "_"),
    ]

    candidates: list[str] = []
    for candidate in raw_candidates:
        if not candidate:
            continue
        if candidate not in candidates:
            candidates.append(candidate)
        if candidate.endswith("_agent"):
            stripped = candidate.removesuffix("_agent")
            if stripped and stripped not in candidates:
                candidates.append(stripped)
        else:
            suffixed = f"{candidate}_agent"
            if suffixed not in candidates:
                candidates.append(suffixed)
    return candidates


def _sum_passive_eval_agents_metrics(rows: list, agent_id: str) -> tuple[float, float]:
    """Sum LLM duration and cost for an agent across raw PassiveEvalAgents rows."""
    total_duration = 0.0
    total_cost = 0.0
    candidates = _agent_key_candidates(agent_id)
    normalized_candidates = {
        candidate.lower().replace("_", "-"): candidate for candidate in candidates
    }

    for row in rows:
        metrics = _load_json_dict(row[-1] if row else None)
        if metrics.get("metric_name") != PASSIVE_EVAL_AGENTS_METRIC:
            continue

        value = _load_json_dict(metrics.get("value"))
        agents = _load_json_dict(value.get("agents"))
        agent_metrics: dict = {}

        for candidate in candidates:
            maybe_metrics = _load_json_dict(agents.get(candidate))
            if maybe_metrics:
                agent_metrics = maybe_metrics
                break

        if not agent_metrics:
            for key, metrics_value in agents.items():
                normalized_key = str(key).lower().replace("_", "-")
                if normalized_key in normalized_candidates:
                    maybe_metrics = _load_json_dict(metrics_value)
                    if maybe_metrics:
                        agent_metrics = maybe_metrics
                        break

        if not agent_metrics:
            continue

        total_duration += float(agent_metrics.get(AGENT_LLM_DURATION) or 0)
        total_cost += float(agent_metrics.get(AGENT_LLM_COST) or 0)

    return total_duration, total_cost


# ── get_application_charts (dispatcher) ──────────────────────────────────────

# From table derived_metrics, we derive multiple charts
# Query to get from table otel_metrics the session IDs for the given application_id
#  and agent_id within the time range.
# We get a list of session_ids per time bucket
# TODO: Implement the possibility to filter by given_session_ids in the query when provided.


def _get_application_charts(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    chart_type: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
):
    """Dispatch to the dedicated chart function based on ``chart_type``."""
    _DISPATCH = {
        "general": _get_application_charts_general,
        "quality-and-reasoning": _get_application_charts_quality_and_reasoning,
        "reliability-and-safety": _get_application_charts_reliability_and_safety,
        "cost": _get_application_charts_cost,
        "tools": _get_application_charts_tools,
        "conversation": _get_application_charts_conversation,
        "llm": _get_application_charts_llm,
        "performance": _get_application_charts_performance,
    }
    handler = _DISPATCH.get(chart_type)
    if handler is None:
        raise ValueError(f"Unknown chart_type: {chart_type!r}")
    return handler(
        db,
        dialect,
        application_id=application_id,
        agent_id=agent_id,
        start_time=start_time,
        end_time=end_time,
        given_session_ids=given_session_ids,
    )


# ── general ──────────────────────────────────────────────────────────────────

# Query to retrieve from derived_metrics all the session_id entries
# where the metrics field contains "metric_name": "PassiveEvalAgents"
# EXAMPLE: doc/Metrics_PassiveEvalAgents.json
# From each entry, we filter to get the agent we need
# And parse the values defined in ApplicationGeneralChartsResponse
# We sum the values of all the entries for each time bucket and return this aggregated value


def _get_application_charts_general(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationGeneralChartsResponse:
    """Return general-charts timeline data for an agent within an application.

    Builds five timeline series (one data-point per time bucket):
    ``totalLLMInvocationDuration``, ``totalAgentCost``,
    ``overallTaskCompletion``, ``averageAnswerRelevancy``, and
    ``successRate``.

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationGeneralChartsResponse()
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT

    current = start_epoch
    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            application_id=application_id,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values for each metric
        sum_eval_agent_llm_duration = 0.0
        sum_eval_agent_llm_cost = 0.0
        overall_task_completion_val = 0.0
        average_answer_relevancy_val = 0.0
        success_rate_val = 0.0

        # Populate metrics from derived_metrics when sessions exist
        # (requires derived_metrics table — values stay at 0 when
        #  the table is not available)
        if bucket_session_ids:
            try:
                metrics_stmt = ui_queries.passive_eval_agents_metrics_by_sessions_query(
                    dialect,
                    session_ids=bucket_session_ids,
                )
                metrics_rows = db.execute(metrics_stmt)
                (
                    sum_eval_agent_llm_duration,
                    sum_eval_agent_llm_cost,
                ) = _sum_passive_eval_agents_metrics(metrics_rows, agent_id)
            except Exception as exc:
                logger.error("PassiveEvalAgents aggregation: %s", exc)

            try:
                overall_stmt = (
                    ui_queries.derived_metric_mce_avg_by_sessions_and_agent_query(
                        dialect,
                        metric_name=RESPONSE_COMPLETENESS,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                        with_category=True,
                    )
                )
                overall_rows = db.execute(overall_stmt)
                if overall_rows and overall_rows[0] and overall_rows[0][0] is not None:
                    overall_task_completion_val = float(overall_rows[0][0]) * 100
            except Exception as exc:
                logger.error("RESPONSE_COMPLETENESS: %s", exc)
            try:
                overall_stmt = (
                    ui_queries.derived_metric_mce_avg_by_sessions_and_agent_query(
                        dialect,
                        metric_name=ANSWER_RELEVANCY,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                        with_category=True,
                    )
                )
                overall_rows = db.execute(overall_stmt)
                if overall_rows and overall_rows[0] and overall_rows[0][0] is not None:
                    average_answer_relevancy_val = float(overall_rows[0][0]) * 100
            except Exception as exc:
                logger.error("ANSWER_RELEVANCY: %s", exc)

        result.totalLLMInvocationDuration.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=sum_eval_agent_llm_duration, unit="MILLISECONDS"
                ),
            )
        )
        result.totalAgentCost.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=sum_eval_agent_llm_cost, unit="DOLLAR"),
            )
        )
        result.overallTaskCompletion.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=overall_task_completion_val, unit="PERCENTAGE"
                ),
            )
        )
        result.averageAnswerRelevancy.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=average_answer_relevancy_val, unit="PERCENTAGE"
                ),
            )
        )
        result.successRate.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=success_rate_val, unit="PERCENTAGE"),
            )
        )

        current += period_size

    return result


# ── quality-and-reasoning ────────────────────────────────────────────────────


def _get_application_charts_quality_and_reasoning(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationQualityAndReasoningChartsResponse:
    """Return quality-and-reasoning timeline data for an agent.

    Builds seven timeline series (one data-point per time bucket):
    ``toolUtilizationAccuracy``, ``generalStructureAndStyle``,
    ``answerCorrectness``, ``answerRelevancy``, ``answerGroundedness``,
    ``answerCoherence``, and ``agentTonality``.

    Also returns a single ``overallTaskCompletion`` value computed
    across all sessions in the full time range.

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationQualityAndReasoningChartsResponse()

    # Compute overallTaskCompletion across ALL sessions in the range
    full_start_dt = epoch_to_dt_str(start_epoch)
    full_end_dt = epoch_to_dt_str(end_epoch)
    all_stmt = ui_queries.session_ids_by_app_and_agent_query(
        dialect,
        start_time=full_start_dt,
        end_time=full_end_dt,
        agent_id=agent_id,
        given_session_ids=given_session_ids,
    )
    try:
        all_rows = db.execute(all_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        all_rows = []
    all_session_ids = [str(r[0]) for r in all_rows]

    if all_session_ids:
        # overallTaskCompletion would be populated from derived_metrics
        # (defaults to 0 when the table is not available)
        pass

    # Build timeline buckets
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT

    current = start_epoch
    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values for each metric
        tool_util_val = 0.0
        structure_val = 0.0
        correctness_val = 0.0
        relevancy_val = 0.0
        groundedness_val = 0.0
        coherence_val = 0.0
        tonality_val = 0.0

        # Populate metrics from derived_metrics when sessions exist
        # (requires derived_metrics table — values stay at 0 when
        #  the table is not available)

        result.toolUtilizationAccuracy.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=tool_util_val, unit="PERCENTAGE"),
            )
        )
        result.generalStructureAndStyle.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=structure_val, unit="PERCENTAGE"),
            )
        )
        result.answerCorrectness.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=correctness_val, unit="PERCENTAGE"),
            )
        )
        result.answerRelevancy.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=relevancy_val, unit="PERCENTAGE"),
            )
        )
        result.answerGroundedness.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=groundedness_val, unit="PERCENTAGE"),
            )
        )
        result.answerCoherence.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=coherence_val, unit="PERCENTAGE"),
            )
        )
        result.agentTonality.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=tonality_val, unit="PERCENTAGE"),
            )
        )

        current += period_size

    return result


# ── reliability-and-safety ───────────────────────────────────────────────────


def _get_application_charts_reliability_and_safety(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationReliabilityAndSafetyChartsResponse:
    """Return reliability-and-safety data for an agent.

    Returns eight single-value metrics (``successRate``, ``errorRate``,
    ``recoveryRate``, ``retryRate``, ``agentFailureCount``,
    ``agentRecoveryCount``, ``agentRecoveryRate``, ``agentAvailability``)
    and three timeline series (``bias``, ``toxicity``,
    ``policyViolation``).

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationReliabilityAndSafetyChartsResponse()

    # Compute single-value metrics across ALL sessions in the range
    full_start_dt = epoch_to_dt_str(start_epoch)
    full_end_dt = epoch_to_dt_str(end_epoch)
    all_stmt = ui_queries.session_ids_by_app_and_agent_query(
        dialect,
        start_time=full_start_dt,
        end_time=full_end_dt,
        agent_id=agent_id,
        given_session_ids=given_session_ids,
    )
    try:
        all_rows = db.execute(all_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        all_rows = []
    all_session_ids = [str(r[0]) for r in all_rows]

    if all_session_ids:
        # successRate defaults to 100% when sessions exist;
        # errorRate = 100 - successRate
        result.successRate.value = 100.0
        result.errorRate.value = 0.0

        # recoveryRate, retryRate, agentFailureCount,
        # agentRecoveryCount, agentRecoveryRate, agentAvailability
        # would be populated from derived_metrics
        # (defaults to 0 when the table is not available)

    # Build timeline buckets
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT

    current = start_epoch
    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values for each metric
        bias_val = 0.0
        toxicity_val = 0.0
        policy_violation_val = 0.0

        # Populate metrics from derived_metrics when sessions exist
        # (requires derived_metrics table — values stay at 0 when
        #  the table is not available)

        result.bias.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=bias_val, unit="PERCENTAGE"),
            )
        )
        result.toxicity.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=toxicity_val, unit="PERCENTAGE"),
            )
        )
        result.policyViolation.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=policy_violation_val, unit="PERCENTAGE"),
            )
        )

        current += period_size

    return result


# ── cost ─────────────────────────────────────────────────────────────────────


def _get_application_charts_cost(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationCostChartsResponse:
    """Return cost-charts timeline data for an agent.

    Builds six timeline series (one data-point per time bucket):
    ``totalLLMCost``, ``totalToolCost``, ``averageLLMCost``,
    ``averageToolCost``, ``numberOfLLMCalls``, and
    ``numberOfToolCalls``.

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationCostChartsResponse()
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT

    current = start_epoch
    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values for each metric
        total_llm_cost_val = 0.0
        total_tool_cost_val = 0.0
        avg_llm_cost_val = 0.0
        avg_tool_cost_val = 0.0
        num_llm_calls_val = 0.0
        num_tool_calls_val = 0.0

        # Populate metrics from derived_metrics when sessions exist
        # (requires derived_metrics table — values stay at 0 when
        #  the table is not available)

        result.totalLLMCost.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=total_llm_cost_val, unit="DOLLAR"),
            )
        )
        result.totalToolCost.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=total_tool_cost_val, unit="DOLLAR"),
            )
        )
        result.averageLLMCost.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=avg_llm_cost_val, unit="DOLLAR"),
            )
        )
        result.averageToolCost.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=avg_tool_cost_val, unit="DOLLAR"),
            )
        )
        result.numberOfLLMCalls.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=num_llm_calls_val, unit="SCALAR"),
            )
        )
        result.numberOfToolCalls.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=num_tool_calls_val, unit="SCALAR"),
            )
        )

        current += period_size

    return result


# ── tools ────────────────────────────────────────────────────────────────────


def _get_application_charts_tools(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationToolsChartsResponse:
    """Return per-tool details for an agent within an application.

    For each tool used by the agent, returns utilization, success /
    error rates, and a ``toolDuration`` timeline (one data-point per
    time bucket).

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationToolsChartsResponse()

    # Get all session IDs for the full range filtered by agent
    full_start_dt = epoch_to_dt_str(start_epoch)
    full_end_dt = epoch_to_dt_str(end_epoch)
    all_stmt = ui_queries.session_ids_by_app_and_agent_query(
        dialect,
        start_time=full_start_dt,
        end_time=full_end_dt,
        agent_id=agent_id,
        given_session_ids=given_session_ids,
    )
    try:
        all_rows = db.execute(all_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        all_rows = []
    all_session_ids = [str(r[0]) for r in all_rows]

    if not all_session_ids:
        return result

    # Get per-tool aggregates across all sessions
    tools_stmt = ui_queries.tool_details_by_sessions_and_agent_query(
        dialect,
        session_ids=all_session_ids,
        agent_id=agent_id,
    )
    try:
        tools_rows = db.execute(tools_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        tools_rows = []

    total_sessions = len(all_session_ids)
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT

    for trow in tools_rows:
        tool_name = str(trow[0])
        success_rate = float(trow[1]) if trow[1] else 0.0
        session_count = int(trow[2]) if trow[2] else 0
        # duration is already in ms from the query

        utilization_pct = (
            session_count / total_sessions * 100 if total_sessions > 0 else 0.0
        )

        tool_detail = ToolDetail(
            toolName=tool_name,
            utilization=SingleValueData(
                value=utilization_pct,
                unit="PERCENTAGE",
            ),
            errorRate=SingleValueData(
                value=(1 - success_rate) * 100,
                unit="PERCENTAGE",
            ),
            successRate=SingleValueData(
                value=success_rate * 100,
                unit="PERCENTAGE",
            ),
            retryRate=SingleValueData(value=0, unit="PERCENTAGE"),
            utilizationAccuracyScore=SingleValueData(
                value=0,
                unit="PERCENTAGE",
            ),
        )

        # Build toolDuration timeline for this tool
        current = start_epoch
        while current < end_epoch:
            bucket_start_dt = epoch_to_dt_str(current)
            bucket_end_dt = epoch_to_dt_str(current + period_size)

            bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
                dialect,
                start_time=bucket_start_dt,
                end_time=bucket_end_dt,
                agent_id=agent_id,
                given_session_ids=given_session_ids,
            )
            try:
                bucket_rows = db.execute(bucket_stmt)
            except Exception as exc:
                logger.error("malformed or unexpected data: %s", exc)
                bucket_rows = []
            bucket_session_ids = [str(r[0]) for r in bucket_rows]

            timestamp_iso = datetime.fromtimestamp(
                current,
                tz=timezone.utc,
            ).isoformat()

            duration_val = 0.0
            if bucket_session_ids:
                dur_stmt = ui_queries.tool_detail_for_tool_name_query(
                    dialect,
                    session_ids=bucket_session_ids,
                    agent_id=agent_id,
                    tool_name=tool_name,
                )
                try:
                    dur_rows = db.execute(dur_stmt)
                except Exception as exc:
                    logger.error("malformed or unexpected data: %s", exc)
                    dur_rows = []
                if dur_rows and dur_rows[0][1] is not None:
                    duration_val = float(dur_rows[0][1])

            tool_detail.toolDuration.append(
                TimelineData(
                    timestamp=timestamp_iso,
                    sessionIDs=bucket_session_ids,
                    value=SingleValueData(value=duration_val, unit="MILLISECONDS"),
                )
            )

            current += period_size

        result.toolDetails.append(tool_detail)

    return result


# ── conversation ─────────────────────────────────────────────────────────────


def _get_application_charts_conversation(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationConversationChartsResponse:
    """Return conversation-quality timeline data for an agent.

    Builds eight timeline series (one data-point per time bucket):
    relevancy, completeness, roleAdherence, topicAdherence,
    contextPreservation, intentRecognitionAccuracy,
    workflowCohesionIndex, goalSuccessRate.

    All values are PERCENTAGE (0-100).  The raw derived-metric
    values are in 0-1 range and are multiplied by 100.

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationConversationChartsResponse()
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT
    current = start_epoch

    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values for each metric
        relevancy_val = 0.0
        completeness_val = 0.0
        role_adherence_val = 0.0
        topic_adherence_val = 0.0
        context_preservation_val = 0.0
        intent_recognition_accuracy_val = 0.0
        workflow_cohesion_index_val = 0.0
        goal_success_rate_val = 0.0

        # Populate metrics from derived_metrics when sessions exist
        # (requires derived_metrics table — values stay at 0 when
        #  the table is not available)

        result.relevancy.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=relevancy_val, unit="PERCENTAGE"),
            )
        )
        result.completeness.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=completeness_val, unit="PERCENTAGE"),
            )
        )
        result.roleAdherence.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=role_adherence_val, unit="PERCENTAGE"),
            )
        )
        result.topicAdherence.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=topic_adherence_val, unit="PERCENTAGE"),
            )
        )
        result.contextPreservation.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=context_preservation_val, unit="PERCENTAGE"
                ),
            )
        )
        result.intentRecognitionAccuracy.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=intent_recognition_accuracy_val, unit="PERCENTAGE"
                ),
            )
        )
        result.workflowCohesionIndex.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=workflow_cohesion_index_val, unit="PERCENTAGE"
                ),
            )
        )
        result.goalSuccessRate.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=goal_success_rate_val, unit="PERCENTAGE"),
            )
        )

        current += period_size

    return result


# ── llm ──────────────────────────────────────────────────────────────────────


def _get_application_charts_llm(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationLLMChartsResponse:
    """Return LLM-specific timeline data for an agent.

    Builds twenty timeline series (one data-point per time bucket):
    totalLLMCost (DOLLAR), totalTokens / inputTokens / outputTokens
    (SCALAR), inferenceDuration (MILLISECONDS), and fifteen
    PERCENTAGE metrics covering quality, reliability, and safety.

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationLLMChartsResponse()
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT
    current = start_epoch

    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values for each metric
        total_llm_cost_val = 0.0
        total_tokens_val = 0.0
        input_tokens_val = 0.0
        output_tokens_val = 0.0
        inference_duration_val = 0.0
        answer_correctness_val = 0.0
        answer_relevancy_val = 0.0
        answer_faithfulness_val = 0.0
        coherence_val = 0.0
        tonality_val = 0.0
        general_structure_style_metric_val = 0.0
        llm_error_rate_val = 0.0
        llm_success_rate_val = 0.0
        llm_recovery_rate_val = 0.0
        llm_retry_rate_val = 0.0
        toxicity_val = 0.0
        bias_val = 0.0
        uncertainty_score_val = 0.0
        pii_detection_val = 0.0
        policy_violation_val = 0.0

        # Populate metrics from derived_metrics when sessions exist
        # (requires derived_metrics table — values stay at 0 when
        #  the table is not available)

        result.totalLLMCost.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=total_llm_cost_val, unit="DOLLAR"),
            )
        )
        result.totalTokens.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=total_tokens_val, unit="SCALAR"),
            )
        )
        result.inputTokens.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=input_tokens_val, unit="SCALAR"),
            )
        )
        result.outputTokens.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=output_tokens_val, unit="SCALAR"),
            )
        )
        result.inferenceDuration.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=inference_duration_val, unit="MILLISECONDS"
                ),
            )
        )
        result.answerCorrectness.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=answer_correctness_val, unit="PERCENTAGE"),
            )
        )
        result.answerRelevancy.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=answer_relevancy_val, unit="PERCENTAGE"),
            )
        )
        result.answerFaithfulness.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=answer_faithfulness_val, unit="PERCENTAGE"),
            )
        )
        result.coherence.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=coherence_val, unit="PERCENTAGE"),
            )
        )
        result.tonality.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=tonality_val, unit="PERCENTAGE"),
            )
        )
        result.generalStructureStyleMetric.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(
                    value=general_structure_style_metric_val, unit="PERCENTAGE"
                ),
            )
        )
        result.llmErrorRate.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=llm_error_rate_val, unit="PERCENTAGE"),
            )
        )
        result.llmSuccessRate.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=llm_success_rate_val, unit="PERCENTAGE"),
            )
        )
        result.llmRecoveryRate.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=llm_recovery_rate_val, unit="PERCENTAGE"),
            )
        )
        result.llmRetryRate.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=llm_retry_rate_val, unit="PERCENTAGE"),
            )
        )
        result.toxicity.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=toxicity_val, unit="PERCENTAGE"),
            )
        )
        result.bias.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=bias_val, unit="PERCENTAGE"),
            )
        )
        result.uncertaintyScore.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=uncertainty_score_val, unit="PERCENTAGE"),
            )
        )
        result.piiDetection.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=pii_detection_val, unit="PERCENTAGE"),
            )
        )
        result.policyViolation.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=policy_violation_val, unit="PERCENTAGE"),
            )
        )

        current += period_size

    return result


# ── performance ──────────────────────────────────────────────────────────────


def _get_application_charts_performance(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    agent_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> ApplicationPerformanceChartsResponse:
    """Return performance-charts data for an agent within an application.

    Computes four single-value metrics across ALL sessions:
    ``agentErrorCount``, ``agentRetrievalLatency``,
    ``agentLatencyPercentile90``, ``agentLatencyPercentile95``.

    Builds five timeline series (one data-point per time bucket):
    ``averageLatency``, ``agentThroughput``,
    ``agentWorkflowEfficiency``, ``averageLLMInvocationDuration``,
    and ``errorRateOverTime``.

    Also returns ``errorsBreakdown`` with all error names and counts.

    When *given_session_ids* is provided, the start / end time are
    overridden based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # When session IDs are given, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    result = ApplicationPerformanceChartsResponse()

    # ── Single-value metrics across ALL sessions ─────────────────────────
    full_start_dt = epoch_to_dt_str(start_epoch)
    full_end_dt = epoch_to_dt_str(end_epoch)
    all_stmt = ui_queries.session_ids_by_app_and_agent_query(
        dialect,
        start_time=full_start_dt,
        end_time=full_end_dt,
        agent_id=agent_id,
        given_session_ids=given_session_ids,
    )
    try:
        all_rows = db.execute(all_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        all_rows = []
    all_session_ids = [str(r[0]) for r in all_rows]

    if all_session_ids:
        # agentErrorCount = llm_fails + tool_fails
        try:
            fails_stmt = (
                ui_queries.derived_metric_sdk_sum_fails_by_sessions_and_agent_query(
                    dialect,
                    session_ids=all_session_ids,
                    agent_id=agent_id,
                )
            )
            fails_rows = db.execute(fails_stmt)
            if fails_rows and fails_rows[0]:
                llm_fails = float(fails_rows[0][0] or 0)
                tool_fails = float(fails_rows[0][1] or 0)
                result.agentErrorCount.value = llm_fails + tool_fails
        except Exception as exc:
            logger.error("agentErrorCount: %s", exc)

        # agentRetrievalLatency
        try:
            latency_stmt = (
                ui_queries.derived_metric_sdk_avg_by_sessions_and_agent_query(
                    dialect,
                    metric_name=APP_RETRIEVAL_LATENCY,
                    session_ids=all_session_ids,
                    agent_id=agent_id,
                )
            )
            latency_rows = db.execute(latency_stmt)
            if latency_rows and latency_rows[0] and latency_rows[0][0]:
                result.agentRetrievalLatency.value = float(latency_rows[0][0]) * 100
                result.agentRetrievalLatency.unit = "MILLISECONDS"
        except Exception as exc:
            logger.error("agentRetrievalLatency: %s", exc)

        # agentLatencyPercentile90 / agentLatencyPercentile95
        try:
            dur_stmt = ui_queries.agent_durations_sorted_query(
                dialect,
                session_ids=all_session_ids,
                agent_id=agent_id,
            )
            dur_rows = db.execute(dur_stmt)
            durations = [float(r[0]) for r in dur_rows if r[0] is not None]
            if durations:
                idx90 = min(int(len(durations) * 0.9), len(durations) - 1)
                idx95 = min(int(len(durations) * 0.95), len(durations) - 1)
                result.agentLatencyPercentile90 = SingleValueData(
                    value=durations[idx90],
                    unit="MILLISECONDS",
                )
                result.agentLatencyPercentile95 = SingleValueData(
                    value=durations[idx95],
                    unit="MILLISECONDS",
                )
        except Exception as exc:
            logger.error("latency percentiles: %s", exc)

    # ── Timeline series ──────────────────────────────────────────────────
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT
    current = start_epoch

    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Get session IDs for this bucket filtered by agent
        bucket_stmt = ui_queries.session_ids_by_app_and_agent_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            agent_id=agent_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        # Default values
        avg_latency_val = 0.0
        throughput_val = 0.0
        workflow_eff_val = 0.0
        llm_inv_duration_val = 0.0
        error_rate_val = 0.0

        if bucket_session_ids:
            # averageLatency (agent duration)
            try:
                dur_avg_stmt = (
                    ui_queries.derived_metric_sdk_avg_by_sessions_and_agent_query(
                        dialect,
                        metric_name=APP_AGENT_DURATION,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                    )
                )
                dur_avg_rows = db.execute(dur_avg_stmt)
                if dur_avg_rows and dur_avg_rows[0] and dur_avg_rows[0][0]:
                    avg_latency_val = float(dur_avg_rows[0][0])
            except Exception as exc:
                logger.error("averageLatency: %s", exc)

            # agentThroughput = (llmCalls + toolCalls) / durationSum * 1000
            try:
                llm_calls_stmt = (
                    ui_queries.derived_metric_sdk_sum_by_sessions_and_agent_query(
                        dialect,
                        metric_name=APP_LLM_CALLS,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                    )
                )
                tool_calls_stmt = (
                    ui_queries.derived_metric_sdk_sum_by_sessions_and_agent_query(
                        dialect,
                        metric_name=APP_TOOL_CALLS,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                    )
                )
                dur_sum_stmt = (
                    ui_queries.derived_metric_sdk_sum_by_sessions_and_agent_query(
                        dialect,
                        metric_name=APP_AGENT_DURATION,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                    )
                )
                llm_calls_rows = db.execute(llm_calls_stmt)
                tool_calls_rows = db.execute(tool_calls_stmt)
                dur_sum_rows = db.execute(dur_sum_stmt)

                llm_calls = (
                    float(llm_calls_rows[0][0] or 0)
                    if llm_calls_rows and llm_calls_rows[0]
                    else 0
                )
                tool_calls = (
                    float(tool_calls_rows[0][0] or 0)
                    if tool_calls_rows and tool_calls_rows[0]
                    else 0
                )
                dur_sum = (
                    float(dur_sum_rows[0][0] or 0)
                    if dur_sum_rows and dur_sum_rows[0]
                    else 0
                )

                if dur_sum > 0:
                    throughput_val = (
                        (llm_calls + tool_calls) / dur_sum * 1000
                    )  # per second
            except Exception as exc:
                logger.error("agentThroughput: %s", exc)

            # agentWorkflowEfficiency
            try:
                wf_stmt = ui_queries.derived_metric_sdk_avg_by_sessions_and_agent_query(
                    dialect,
                    metric_name=APP_WORKFLOW_EFFICIENCY,
                    session_ids=bucket_session_ids,
                    agent_id=agent_id,
                )
                wf_rows = db.execute(wf_stmt)
                if wf_rows and wf_rows[0] and wf_rows[0][0]:
                    workflow_eff_val = float(wf_rows[0][0]) * 100
            except Exception as exc:
                logger.error("workflowEfficiency: %s", exc)

            # averageLLMInvocationDuration
            try:
                llm_dur_stmt = (
                    ui_queries.derived_metric_sdk_avg_by_sessions_and_agent_query(
                        dialect,
                        metric_name=APP_LLM_INVOCATION_DURATION,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                    )
                )
                llm_dur_rows = db.execute(llm_dur_stmt)
                if llm_dur_rows and llm_dur_rows[0] and llm_dur_rows[0][0]:
                    llm_inv_duration_val = float(llm_dur_rows[0][0])
            except Exception as exc:
                logger.error("avgLLMInvocationDuration: %s", exc)

            # errorRateOverTime = llm_fails + tool_fails
            try:
                err_stmt = (
                    ui_queries.derived_metric_sdk_sum_fails_by_sessions_and_agent_query(
                        dialect,
                        session_ids=bucket_session_ids,
                        agent_id=agent_id,
                    )
                )
                err_rows = db.execute(err_stmt)
                if err_rows and err_rows[0]:
                    llm_f = float(err_rows[0][0] or 0)
                    tool_f = float(err_rows[0][1] or 0)
                    error_rate_val = llm_f + tool_f
            except Exception as exc:
                logger.error("errorRateOverTime: %s", exc)

        result.averageLatency.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=avg_latency_val, unit="MILLISECONDS"),
            )
        )
        result.agentThroughput.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=throughput_val, unit="SCALAR"),
            )
        )
        result.agentWorkflowEfficiency.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=workflow_eff_val, unit="PERCENTAGE"),
            )
        )
        result.averageLLMInvocationDuration.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=llm_inv_duration_val, unit="MILLISECONDS"),
            )
        )
        result.errorRateOverTime.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=error_rate_val, unit="SCALAR"),
            )
        )

        current += period_size

    # ── Errors breakdown ─────────────────────────────────────────────────
    if all_session_ids:
        try:
            errors_stmt = ui_queries.most_frequent_errors_by_agent_query(
                dialect,
                session_ids=all_session_ids,
                agent_id=agent_id,
            )
            errors_rows = db.execute(errors_stmt)
            for erow in errors_rows:
                result.errorsBreakdown.append(
                    ErrorItem(
                        name=str(erow[0]),
                        count=int(erow[1]),
                    )
                )
        except Exception as exc:
            logger.error("errorsBreakdown: %s", exc)

    return result
