#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Evaluate a single session and output trajectory_score + intermediate metrics.

Usage (local):
  SESSION_ID=abc-123 python -m stateful_evals_be.scripts.run_session_eval

All configuration is via environment variables:
  SESSION_ID          (required) The session to evaluate
  CLICKHOUSE_*        Span database settings consumed by the API library
  NEO4J_*             Metric database settings (only when PUSH_METRICS=true)
  LLM_API_KEY         LLM API key
  LLM_MODEL_NAME      Model name (default: gpt-4o)
  LLM_BASE_MODEL_URL  Model base URL (default: https://api.openai.com/v1)
  FATALITY_THRESHOLD  Fatality threshold (default: 0.5)
  HIGH_LEVEL_METRIC_SUITE  legacy_v1 (default) or paper_v1
  POLICY_TEXT         Optional policy text override
  OUTPUT_FILE         Optional path to write JSON output (default: stdout only)
  PUSH_METRICS        Set to "true" to persist trajectory_score via the API library
"""

import json
import logging
import os
import sys
import time

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("run_session_eval")

try:
    import litellm

    litellm.suppress_debug_info = True
except ImportError:
    pass
logging.getLogger("LiteLLM").setLevel(logging.WARNING)


def _push_trajectory_score(
    session_id: str,
    trajectory_score: int,
) -> None:
    """Persist the existing session-level score through the API library."""
    from stateful_evals_be.integrations.oxp import local_api_client

    payload = {
        "metrics": [
            {
                "name": "trajectory_score",
                "value": trajectory_score,
                "provider": "stateful_evals",
                "metric_id": None,
                "source": "StatefulEval",
                "reasoning": None,
            }
        ]
    }

    try:
        with local_api_client(persist_metrics=True) as client:
            result = client.write_session_metrics(session_id, payload["metrics"])
            written = result.get("written", 0)
            errors = result.get("errors", [])
            if errors:
                for err in errors:
                    logger.error("Push error: %s", err)
            else:
                logger.info(
                    "Persisted trajectory_score=%d for session %s (%d written)",
                    trajectory_score,
                    session_id,
                    written,
                )
    except Exception as exc:
        logger.error("Failed to persist trajectory_score for %s: %s", session_id, exc)


def main() -> None:
    session_id = os.getenv("SESSION_ID", "").strip()
    if not session_id:
        logger.error("SESSION_ID environment variable is required")
        sys.exit(1)

    llm_api_key = os.getenv("LLM_API_KEY", "")
    llm_model_name = os.getenv("LLM_MODEL_NAME", "gpt-4o")
    llm_base_model_url = os.getenv("LLM_BASE_MODEL_URL", "https://api.openai.com/v1")
    fatality_threshold = float(os.getenv("FATALITY_THRESHOLD", "0.5"))
    high_level_metric_suite = os.getenv("HIGH_LEVEL_METRIC_SUITE", "legacy_v1").strip()
    trajectory_metrics_value = os.getenv("TRAJECTORY_METRICS", "").strip()
    trajectory_metrics = (
        [item.strip() for item in trajectory_metrics_value.split(",") if item.strip()]
        if trajectory_metrics_value
        else None
    )
    policy_text = os.getenv("POLICY_TEXT", "").strip() or None
    output_file = os.getenv("OUTPUT_FILE", "").strip() or None
    push_metrics = os.getenv("PUSH_METRICS", "").strip().lower() in ("true", "1", "yes")

    from metrics_computation_engine.models.requests import LLMJudgeConfig
    from stateful_evals_be import evaluate_session
    from stateful_evals_be.models.requests import SamplingConfig, TemporalMetricOptions

    sampling_strategy = os.getenv("SAMPLING_STRATEGY", "none").strip().lower()
    sampling_cfg: SamplingConfig | None = None
    if sampling_strategy == "tail_weighted":
        sampling_cfg = SamplingConfig(
            strategy="tail_weighted",
            early_rate=float(os.getenv("SAMPLING_EARLY_RATE", "0.25")),
            mid_rate=float(os.getenv("SAMPLING_MID_RATE", "0.60")),
        )
        logger.info(
            "Sampling enabled: strategy=tail_weighted | early_rate=%.2f | mid_rate=%.2f",
            sampling_cfg.early_rate,
            sampling_cfg.mid_rate,
        )

    llm_config = LLMJudgeConfig(
        LLM_MODEL_NAME=llm_model_name,
        LLM_BASE_MODEL_URL=llm_base_model_url,
        LLM_API_KEY=llm_api_key,
    )

    options = TemporalMetricOptions(
        use_fatal_mode=True,
        fatality_threshold=fatality_threshold,
        high_level_metric_suite=high_level_metric_suite,
        trajectory_metrics=trajectory_metrics,
        sampling=sampling_cfg,
    )

    logger.info("Evaluating session: %s", session_id)
    logger.info("LLM model: %s", llm_model_name)

    t0 = time.time()
    result = evaluate_session(
        session_id,
        llm_config=llm_config,
        options=options,
        policy_override=policy_text,
    )
    elapsed = time.time() - t0

    result_dict = result.model_dump()
    result_dict["eval_duration_seconds"] = round(elapsed, 2)

    output = {
        "session_id": session_id,
        "trajectory_score": result.trajectory_score,
        "high_level_metric_suite": result.high_level_metric_suite,
        "eval_duration_seconds": round(elapsed, 2),
        "total_spans": result.total_spans,
        "mce_spans_evaluated": result.mce_spans_evaluated,
        "spans_sampled_out": result.spans_sampled_out,
        "unsatisfied_intents": result.unsatisfied_intents,
        "total_failures": result.total_failures,
        "fatal_failures_count": len(result.fatal_failures),
        "minor_failures_count": len(result.minor_failures),
        "current_score": result.current_score,
        "avg_score": result.avg_score,
        "token_usage": result.token_usage.model_dump()
        if hasattr(result.token_usage, "model_dump")
        else {},
        "cost_estimate": result.cost_estimate.model_dump()
        if hasattr(result.cost_estimate, "model_dump")
        else {},
        "error": result.error,
        "span_metrics": [
            m.model_dump() if hasattr(m, "model_dump") else m
            for m in getattr(
                result, "span_metric_results", getattr(result, "span_metrics", [])
            )
        ],
        "fatal_failures": [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in result.fatal_failures
        ],
        "minor_failures": [
            f.model_dump() if hasattr(f, "model_dump") else f
            for f in result.minor_failures
        ],
        "intent_states": [
            s.model_dump() if hasattr(s, "model_dump") else s
            for s in result.intent_states
        ],
        "high_level_metrics": result.high_level_metrics,
    }
    if result.trajectory_metric_set is not None:
        output["trajectory_metric_set"] = result.trajectory_metric_set
        output["trajectory_metrics"] = result.trajectory_metrics

    output_json = json.dumps(output, indent=2, default=str)

    if result.error:
        logger.error("Evaluation error: %s", result.error)
    else:
        logger.info(
            "Done: trajectory_score=%s  spans=%d  fatal=%d  minor=%d  "
            "unsatisfied_intents=%d  duration=%.1fs",
            result.trajectory_score,
            result.total_spans,
            len(result.fatal_failures),
            len(result.minor_failures),
            result.unsatisfied_intents,
            elapsed,
        )

    print(output_json)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output_json)
        logger.info("Output written to: %s", output_file)

    if push_metrics and not result.error and result.trajectory_score is not None:
        _push_trajectory_score(session_id, result.trajectory_score)
    elif push_metrics and result.error:
        logger.warning("Skipping metric push due to evaluation error")

    sys.exit(0 if not result.error else 1)


if __name__ == "__main__":
    main()
