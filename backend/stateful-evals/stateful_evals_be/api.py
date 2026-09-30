#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Public, in-process evaluation API. No database or service is required."""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from metrics_computation_engine.models.requests import LLMJudgeConfig

from stateful_evals_be.evaluation.engine import EvaluationEngine
from stateful_evals_be.evaluation.processor import (
    CORE_METRICS,
    TemporalMetricsProcessor as TemporalMetricsProcessor,
)
from stateful_evals_be.models.requests import SessionResult, TemporalMetricOptions
from stateful_evals_be.models.spans import SpanInput, SpanRecord as SpanRecord
from stateful_evals_be.integrations.oxp import SessionSpanClient


def evaluate_spans(
    spans: Iterable[SpanInput],
    *,
    session_id: str,
    llm_config: LLMJudgeConfig,
    options: TemporalMetricOptions | None = None,
    policy_override: str | None = None,
) -> SessionResult:
    """Evaluate one session's OTel-format spans, without fetching or persisting.

    A fresh processor is used for each call. Model calls can incur costs.
    The caller owns credentials, loading spans, scheduling and result storage.
    """
    return EvaluationEngine(llm_config=llm_config, options=options).evaluate_spans(
        spans, session_id=session_id, policy_override=policy_override
    )


def evaluate_file(
    path: str | Path,
    *,
    llm_config: LLMJudgeConfig,
    session_id: str | None = None,
    options: TemporalMetricOptions | None = None,
    policy_override: str | None = None,
) -> SessionResult:
    """Evaluate one exported JSON/JSONL trajectory without a database.

    The session ID is inferred from the export unless overridden. Invalid exports
    raise ValueError before any model calls; evaluation errors use SessionResult.
    """
    from stateful_evals_be.integrations.files import load_trajectory_file

    selected_id, spans = load_trajectory_file(path, session_id=session_id)
    return evaluate_spans(
        spans,
        session_id=selected_id,
        llm_config=llm_config,
        options=options,
        policy_override=policy_override,
    )


def evaluate_session(
    session_id: str,
    *,
    llm_config: LLMJudgeConfig,
    api_client: SessionSpanClient | None = None,
    options: TemporalMetricOptions | None = None,
    policy_override: str | None = None,
) -> SessionResult:
    """Query a completed session through the API library and evaluate its spans.

    With no client, use the API package's database settings. An injected client
    remains caller-owned. Results are returned, not persisted. Retrieval and
    evaluation failures are reported in SessionResult.error, as in the processor.
    """
    from stateful_evals_be.integrations.oxp import (
        fetch_session_spans,
        local_api_client,
    )

    try:
        if api_client is not None:
            spans = fetch_session_spans(api_client, session_id)
        else:
            with local_api_client() as client:
                spans = fetch_session_spans(client, session_id)
    except Exception as exc:
        return SessionResult(session_id=session_id, error=str(exc))
    return evaluate_spans(
        spans,
        session_id=session_id,
        llm_config=llm_config,
        options=options,
        policy_override=policy_override,
    )


def session_result_payload(result: SessionResult) -> dict[str, Any]:
    """Preserve the legacy JSON shape unless optional metrics were requested."""
    payload = result.model_dump(mode="json")
    if result.trajectory_metric_set is None:
        payload.pop("trajectory_metric_set", None)
        payload.pop("trajectory_metrics", None)
    return payload


def available_metrics() -> dict[str, Any]:
    """Return the metric registry formerly exposed by GET /metrics."""
    from stateful_evals_be.evaluation.trajectory_context_metrics import (
        TRAJECTORY_METRIC_SET,
        available_trajectory_metrics,
    )

    return {
        "total_metrics": len(CORE_METRICS),
        "metrics": list(CORE_METRICS),
        "trajectory_metric_set": TRAJECTORY_METRIC_SET,
        "trajectory_metrics": available_trajectory_metrics(),
    }
