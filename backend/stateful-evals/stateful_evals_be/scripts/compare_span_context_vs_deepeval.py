#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compare span-derived metrics with traditional whole-trajectory DeepEval judges."""

from __future__ import annotations

import argparse
import csv
import dataclasses
import json
import os
import shlex
import threading
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from metrics_computation_engine.llm_judge.llm import LLMClient

from stateful_evals_be.evaluation.trajectory_context_metrics import (
    PAPER_METRIC_SUITE,
    build_metric_suite,
    evaluate_metric_suite_batched,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.context_io import (
    load_trajectory_context_artifact,
    trajectory_context_to_payload,
)
from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
    LLMMetricJudge,
)


def _load_env(path: Path | None) -> None:
    if path is None:
        return
    for raw_line in path.expanduser().read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed = shlex.split(value, comments=True, posix=True)
        os.environ[key.strip()] = parsed[0] if parsed else ""


def _read_json(path: Path) -> Any:
    return json.loads(path.expanduser().read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )


def _safe_payload(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, Mapping):
        return {str(key): _safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_payload(item) for item in value]
    return value


def _json_value(value: Any) -> Any:
    if value in (None, ""):
        return None
    if isinstance(value, (Mapping, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _text(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, default=str, indent=2)


def _span_payload(
    attrs: Mapping[str, Any],
    *,
    direction: str,
) -> Any:
    suffix = "input" if direction == "input" else "output"
    candidates = (
        f"ioa_observe.entity.{suffix}",
        f"traceloop.entity.{suffix}",
        f"mas.tool.{suffix}",
        f"mas.{suffix}",
    )
    for key in candidates:
        if attrs.get(key) not in (None, ""):
            return _json_value(attrs[key])
    return None


def build_whole_trajectory_transcript(
    materialized: Mapping[str, Any],
    *,
    user_input: str,
) -> str:
    """Render policy, LLM responses, and tool I/O without semantic accumulation."""
    raw_spans = [
        item for item in materialized.get("spans") or [] if isinstance(item, Mapping)
    ]
    raw_spans.sort(key=lambda item: str(item.get("Timestamp") or ""))

    contracts: list[tuple[str, str]] = []
    seen_contracts: set[tuple[str, str]] = set()
    operations: list[str] = []
    step = 0
    for raw_span in raw_spans:
        attrs = raw_span.get("SpanAttributes") or {}
        if not isinstance(attrs, Mapping):
            continue
        kind = str(
            attrs.get("ioa_observe.span.kind") or attrs.get("traceloop.span.kind") or ""
        ).casefold()
        boundary = str(attrs.get("mas.boundary") or raw_span.get("SpanName") or "")
        if not kind:
            if boundary == "LLMCall":
                kind = "llm"
            elif boundary == "ToolCall":
                kind = "tool"
        if kind not in {"llm", "tool"}:
            continue

        agent = str(
            attrs.get("mas.agent.id") or attrs.get("ioa_observe.agent.id") or "unknown"
        )
        input_payload = _span_payload(attrs, direction="input")
        output_payload = _span_payload(attrs, direction="output")

        if kind == "llm":
            if isinstance(input_payload, Mapping):
                messages = input_payload.get("messages")
                if isinstance(messages, list):
                    for message in messages:
                        if not isinstance(message, Mapping):
                            continue
                        if str(message.get("role") or "").casefold() != "system":
                            continue
                        content = _text(message.get("content"))
                        key = (agent, content)
                        if content and key not in seen_contracts:
                            seen_contracts.add(key)
                            contracts.append(key)

            content = ""
            if isinstance(output_payload, Mapping):
                content = _text(output_payload.get("content"))
                if not content and not output_payload.get("tool_calls"):
                    content = _text(output_payload)
            else:
                content = _text(output_payload)
            if content:
                step += 1
                operations.append(
                    f"STEP {step} | LLM RESPONSE | agent={agent}\n{content}"
                )
            continue

        tool_name = str(
            attrs.get("mas.tool.name")
            or attrs.get("ioa_observe.entity.name")
            or attrs.get("traceloop.entity.name")
            or raw_span.get("SpanName")
            or "unknown"
        )
        step += 1
        operations.append(
            "\n".join(
                [
                    f"STEP {step} | TOOL CALL | agent={agent} | tool={tool_name}",
                    f"INPUT:\n{_text(input_payload) or '[no recorded input]'}",
                    f"OUTPUT:\n{_text(output_payload) or '[no recorded output]'}",
                ]
            )
        )

    contract_text = "\n\n".join(
        f"AGENT CONTRACT | agent={agent}\n{content}" for agent, content in contracts
    )
    operation_text = "\n\n".join(operations)
    return "\n\n".join(
        [
            "ROOT USER REQUEST",
            user_input or "[not recorded]",
            "AGENT CONTRACTS AND POLICIES",
            contract_text or "[not recorded]",
            "ORDERED TRAJECTORY",
            operation_text or "[no LLM or tool operations recorded]",
        ]
    )


class _TrackingDeepEvalModel:
    """Factory wrapper because DeepEval's base class is an optional dependency."""

    @staticmethod
    def create(*, model_name: str, max_tokens: int):
        from deepeval.models import DeepEvalBaseLLM

        class TrackingModel(DeepEvalBaseLLM):
            def __init__(self) -> None:
                self.model_name = model_name
                self.max_tokens = max_tokens
                self._usage = {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                }
                self._usage_lock = threading.Lock()
                self._client = LLMClient(
                    {
                        "LLM_MODEL_NAME": model_name,
                        "LLM_BASE_MODEL_URL": os.getenv("LLM_BASE_MODEL_URL", ""),
                        "LLM_API_KEY": os.getenv("LLM_API_KEY", ""),
                    }
                )
                super().__init__(model_name)

            def load_model(self):
                return self._client

            def generate(self, prompt: str, *args, **kwargs) -> str:
                response = self._client.query(
                    [{"role": "user", "content": str(prompt)}],
                    temperature=0.0,
                    max_tokens=self.max_tokens,
                )
                usage = getattr(response, "usage", None)
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                total_tokens = int(
                    getattr(usage, "total_tokens", 0)
                    or (prompt_tokens + completion_tokens)
                )
                with self._usage_lock:
                    self._usage["prompt_tokens"] += prompt_tokens
                    self._usage["completion_tokens"] += completion_tokens
                    self._usage["total_tokens"] += total_tokens
                return response.choices[0].message.content or ""

            async def a_generate(self, prompt: str, *args, **kwargs) -> str:
                import asyncio

                return await asyncio.to_thread(
                    self.generate,
                    prompt,
                    *args,
                    **kwargs,
                )

            def get_model_name(self) -> str:
                return self.model_name

            def supports_log_probs(self) -> bool:
                return False

            def supports_structured_outputs(self) -> bool:
                return False

            def supports_json_mode(self) -> bool:
                return False

            def usage(self) -> dict[str, int]:
                with self._usage_lock:
                    return dict(self._usage)

        return TrackingModel()


def _traditional_metric(
    metric: Any,
    *,
    test_case: Any,
    model_name: str,
    max_tokens: int,
) -> dict[str, Any]:
    from deepeval.metrics import GEval
    from deepeval.test_case import SingleTurnParams

    model = _TrackingDeepEvalModel.create(
        model_name=model_name,
        max_tokens=max_tokens,
    )
    evaluation_steps = [
        (
            "Read the complete ordered trajectory, including agent contracts, "
            "LLM responses, tool inputs, and tool outputs. Use only this evidence."
        ),
        metric.rubric.strip(),
        (
            "This is a binary evaluation. Return score 1 when the metric passes. "
            "Return score 0 only when the trajectory contains a fatal failure under "
            "the rubric. Explain the decisive trajectory evidence concisely."
        ),
    ]
    judge = GEval(
        name=metric.name,
        evaluation_steps=evaluation_steps,
        evaluation_params=[
            SingleTurnParams.INPUT,
            SingleTurnParams.ACTUAL_OUTPUT,
        ],
        model=model,
        threshold=1.0,
        strict_mode=True,
        async_mode=False,
        verbose_mode=False,
    )
    try:
        measured_score = float(judge.measure(test_case, _show_indicator=False))
        score = 1 if measured_score >= 1.0 else 0
        return {
            "high_level_metric": metric.name,
            "score": score,
            "deepeval_score": measured_score,
            "reasoning": str(judge.reason or ""),
            "error": "",
            "usage": model.usage(),
        }
    except Exception as exc:
        return {
            "high_level_metric": metric.name,
            "score": None,
            "deepeval_score": None,
            "reasoning": "",
            "error": f"{type(exc).__name__}: {exc}",
            "usage": model.usage(),
        }


def evaluate_traditional_deepeval(
    *,
    user_input: str,
    transcript: str,
    model_name: str,
    workers: int,
    max_tokens: int,
) -> list[dict[str, Any]]:
    from deepeval.test_case import LLMTestCase

    test_case = LLMTestCase(input=user_input, actual_output=transcript)
    metrics = list(build_metric_suite(PAPER_METRIC_SUITE))
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(
                _traditional_metric,
                metric,
                test_case=test_case,
                model_name=model_name,
                max_tokens=max_tokens,
            ): metric.name
            for metric in metrics
        }
        for future in as_completed(futures):
            metric_name = futures[future]
            try:
                results[metric_name] = future.result()
            except Exception as exc:
                results[metric_name] = {
                    "high_level_metric": metric_name,
                    "score": None,
                    "reasoning": "",
                    "error": f"{type(exc).__name__}: {exc}",
                    "usage": {},
                }
    return [results[metric.name] for metric in metrics]


def evaluate_span_context(
    *,
    context_path: Path,
    stateful_result_path: Path,
    model_name: str,
) -> list[dict[str, Any]]:
    context, _ = load_trajectory_context_artifact(context_path)
    stateful_result = _read_json(stateful_result_path)
    judge = LLMMetricJudge(model_name=model_name)
    results = evaluate_metric_suite_batched(
        context,
        metric_suite=PAPER_METRIC_SUITE,
        stateful_result=stateful_result,
        judge=judge,
    )
    return [result.to_payload() for result in results]


def evaluate_full_span_pipeline(
    *,
    materialized_path: Path,
    session_id: str,
    model_name: str,
    metric_suite: str = PAPER_METRIC_SUITE,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Rerun span extraction and a named paper metric audit with one model."""
    from metrics_computation_engine.models.requests import LLMJudgeConfig
    from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
    from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext
    from stateful_evals_be.models.requests import TemporalMetricOptions

    materialized = _read_json(materialized_path)
    raw_spans = list(materialized.get("spans") or [])
    config = LLMJudgeConfig(
        LLM_MODEL_NAME=model_name,
        LLM_BASE_MODEL_URL=os.environ["LLM_BASE_MODEL_URL"],
        LLM_API_KEY=os.environ["LLM_API_KEY"],
    )
    processor = TemporalMetricsProcessor(
        llm_config=config,
        options=TemporalMetricOptions(
            use_fatal_mode=True,
            high_level_metric_suite=metric_suite,
            span_judge_max_tokens=4096,
            final_judge_max_tokens=8192,
            reasoning_effort="low",
        ),
    )

    captured: dict[str, TrajectoryContext] = {}
    original_ingest = TrajectoryContext.ingest_span

    def ingest_and_capture(
        self: TrajectoryContext,
        span_dict: dict[str, Any],
        span_index: int,
    ) -> None:
        original_ingest(self, span_dict, span_index)
        captured["context"] = self

    TrajectoryContext.ingest_span = ingest_and_capture
    started = time.time()
    try:
        result = processor.evaluate_spans(raw_spans, session_id=session_id)
    finally:
        TrajectoryContext.ingest_span = original_ingest

    if result.error:
        raise RuntimeError(f"Full span pipeline failed: {result.error}")
    results = [
        dict(item) if isinstance(item, Mapping) else _safe_payload(item)
        for item in result.high_level_metrics
    ]
    _assert_valid_results(results, arm="full span pipeline")

    context = captured.get("context")
    if context is None:
        raise RuntimeError("Full span pipeline did not expose trajectory context")
    stateful_payload = _safe_payload(result)
    stateful_payload["eval_duration_seconds"] = round(time.time() - started, 3)
    context_payload = trajectory_context_to_payload(
        context,
        schema_version="trajectory-context-comparison.v2",
        session_id=session_id,
        metadata={"model": model_name},
    )
    return results, stateful_payload, context_payload


def _assert_valid_results(
    results: Sequence[Mapping[str, Any]],
    *,
    arm: str,
) -> None:
    errors: list[str] = []
    for result in results:
        metric = str(result.get("high_level_metric") or "unknown")
        metadata = result.get("metadata") or {}
        error = result.get("error") or metadata.get("evaluation_error")
        if (
            result.get("score") not in {0, 1}
            or bool(error)
            or bool(metadata.get("evaluation_invalid"))
        ):
            errors.append(f"{metric}: {error or 'invalid score'}")
    if errors:
        preview = "\n".join(errors[:3])
        raise RuntimeError(
            f"{arm} produced {len(errors)} invalid metric result(s):\n{preview}"
        )


def _root_user_input(run_dir: Path) -> str:
    inputs_path = run_dir / "inputs.json"
    if not inputs_path.is_file():
        return ""
    payload = _read_json(inputs_path)
    messages = (payload.get("inputs") or {}).get("user") or []
    return "\n".join(
        str(message.get("content") or "")
        for message in messages
        if isinstance(message, Mapping)
    ).strip()


def _usage(results: Sequence[Mapping[str, Any]], *, nested: bool) -> dict[str, int]:
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for result in results:
        source = (
            ((result.get("metadata") or {}).get("usage") or {})
            if nested
            else (result.get("usage") or {})
        )
        for key in usage:
            usage[key] += int(source.get(key, 0) or 0)
    return usage


def _cost(
    usage: Mapping[str, Any], *, input_per_million: float, output_per_million: float
) -> float:
    return (
        int(usage.get("prompt_tokens", 0) or 0) * input_per_million
        + int(usage.get("completion_tokens", 0) or 0) * output_per_million
    ) / 1_000_000


def _cohen_kappa(pairs: Sequence[tuple[int, int]]) -> float | None:
    if not pairs:
        return None
    observed = sum(left == right for left, right in pairs) / len(pairs)
    left_pass = sum(left == 1 for left, _ in pairs) / len(pairs)
    right_pass = sum(right == 1 for _, right in pairs) / len(pairs)
    expected = left_pass * right_pass + (1 - left_pass) * (1 - right_pass)
    if expected == 1:
        return 1.0 if observed == 1 else None
    return (observed - expected) / (1 - expected)


def build_comparison_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    input_per_million: float,
    output_per_million: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    disagreements: list[dict[str, Any]] = []
    span_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    traditional_usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for record in records:
        for key in span_usage:
            span_usage[key] += int((record.get("span_usage") or {}).get(key, 0))
            traditional_usage[key] += int(
                (record.get("traditional_usage") or {}).get(key, 0)
            )
        span_results = {
            item["high_level_metric"]: item
            for item in record.get("span_context_results") or []
        }
        traditional_results = {
            item["high_level_metric"]: item
            for item in record.get("traditional_results") or []
        }
        for metric_name in sorted(set(span_results) | set(traditional_results)):
            span_result = span_results.get(metric_name) or {}
            traditional_result = traditional_results.get(metric_name) or {}
            span_score = span_result.get("score")
            traditional_score = traditional_result.get("score")
            row = {
                "hash": record.get("hash"),
                "domain": record.get("domain"),
                "scenario": record.get("scenario"),
                "metric": metric_name,
                "span_context_score": span_score,
                "traditional_score": traditional_score,
                "span_reasoning": span_result.get("reasoning", ""),
                "traditional_reasoning": traditional_result.get("reasoning", ""),
                "traditional_error": traditional_result.get("error", ""),
            }
            by_metric[metric_name].append(row)
            if (
                span_score in {0, 1}
                and traditional_score in {0, 1}
                and span_score != traditional_score
            ):
                disagreements.append(row)

    metric_summaries = []
    all_pairs: list[tuple[int, int]] = []
    for metric_name, rows in sorted(by_metric.items()):
        valid = [
            (int(row["span_context_score"]), int(row["traditional_score"]))
            for row in rows
            if row["span_context_score"] in {0, 1}
            and row["traditional_score"] in {0, 1}
        ]
        all_pairs.extend(valid)
        metric_summaries.append(
            {
                "metric": metric_name,
                "valid_pairs": len(valid),
                "agreement_count": sum(left == right for left, right in valid),
                "agreement_rate": (
                    sum(left == right for left, right in valid) / len(valid)
                    if valid
                    else None
                ),
                "cohen_kappa": _cohen_kappa(valid),
                "both_fail": sum(left == 0 and right == 0 for left, right in valid),
                "span_only_fail": sum(
                    left == 0 and right == 1 for left, right in valid
                ),
                "traditional_only_fail": sum(
                    left == 1 and right == 0 for left, right in valid
                ),
                "both_pass": sum(left == 1 and right == 1 for left, right in valid),
                "span_fail_rate": (
                    sum(left == 0 for left, _ in valid) / len(valid) if valid else None
                ),
                "traditional_fail_rate": (
                    sum(right == 0 for _, right in valid) / len(valid)
                    if valid
                    else None
                ),
            }
        )

    return (
        {
            "trajectories": len(records),
            "metric_verdict_pairs": len(all_pairs),
            "overall_agreement_rate": (
                sum(left == right for left, right in all_pairs) / len(all_pairs)
                if all_pairs
                else None
            ),
            "overall_cohen_kappa": _cohen_kappa(all_pairs),
            "overall_both_fail": sum(
                left == 0 and right == 0 for left, right in all_pairs
            ),
            "overall_span_only_fail": sum(
                left == 0 and right == 1 for left, right in all_pairs
            ),
            "overall_traditional_only_fail": sum(
                left == 1 and right == 0 for left, right in all_pairs
            ),
            "overall_both_pass": sum(
                left == 1 and right == 1 for left, right in all_pairs
            ),
            "metric_summaries": metric_summaries,
            "usage": {
                "span_context": {
                    **span_usage,
                    "estimated_cost_usd": _cost(
                        span_usage,
                        input_per_million=input_per_million,
                        output_per_million=output_per_million,
                    ),
                },
                "traditional_deepeval": {
                    **traditional_usage,
                    "estimated_cost_usd": _cost(
                        traditional_usage,
                        input_per_million=input_per_million,
                        output_per_million=output_per_million,
                    ),
                },
            },
        },
        disagreements,
    )


def _write_disagreements(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "hash",
        "domain",
        "scenario",
        "metric",
        "span_context_score",
        "traditional_score",
        "span_reasoning",
        "traditional_reasoning",
        "traditional_error",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--model",
        default="vertex_ai/gemini-2.5-flash",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument(
        "--span-mode",
        choices=("persisted", "full"),
        default="persisted",
        help=(
            "Use an existing trajectory context or rerun sequential span "
            "processing before the paper metric audit."
        ),
    )
    parser.add_argument(
        "--reuse-traditional",
        action="store_true",
        help="Reuse a valid traditional_deepeval.json in the output directory.",
    )
    parser.add_argument("--input-cost-per-million", type=float, default=0.3)
    parser.add_argument("--output-cost-per-million", type=float, default=2.5)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    _load_env(args.env_file)
    manifest = _read_json(args.manifest)
    if not isinstance(manifest, list):
        raise ValueError("Manifest must contain a JSON array")
    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(output_dir / "selection_manifest.json", manifest)

    records: list[dict[str, Any]] = []
    for index, item in enumerate(manifest, 1):
        run_hash = str(item["hash"])
        run_output = output_dir / str(item["domain"]) / run_hash
        record_path = run_output / "paired_evaluation.json"
        if record_path.is_file() and not args.force:
            record = _read_json(record_path)
            if record.get("span_mode", "persisted") == args.span_mode:
                records.append(record)
                print(f"[{index:02d}/{len(manifest)}] {run_hash} resumed", flush=True)
                continue

        context_path = Path(item["trajectory_context"]).expanduser()
        stateful_result_path = Path(item["stateful_result"]).expanduser()
        run_dir = context_path.parents[2]
        materialized_path = context_path.parent / "materialized_trajectory.json"
        if not materialized_path.is_file():
            raise FileNotFoundError(
                f"Materialized trajectory is required: {materialized_path}"
            )
        user_input = _root_user_input(run_dir)
        transcript = build_whole_trajectory_transcript(
            _read_json(materialized_path),
            user_input=user_input,
        )
        run_output.mkdir(parents=True, exist_ok=True)
        (run_output / "traditional_transcript.txt").write_text(
            transcript,
            encoding="utf-8",
        )

        traditional_path = run_output / "traditional_deepeval.json"
        if args.reuse_traditional and traditional_path.is_file():
            traditional_results = _read_json(traditional_path)
            print(
                f"[{index:02d}/{len(manifest)}] {run_hash} traditional reused",
                flush=True,
            )
        else:
            print(
                f"[{index:02d}/{len(manifest)}] {run_hash} traditional DeepEval",
                flush=True,
            )
            traditional_results = evaluate_traditional_deepeval(
                user_input=user_input,
                transcript=transcript,
                model_name=args.model,
                workers=args.workers,
                max_tokens=args.max_tokens,
            )
        _assert_valid_results(traditional_results, arm="traditional DeepEval")
        _write_json(traditional_path, traditional_results)

        print(
            f"[{index:02d}/{len(manifest)}] {run_hash} span {args.span_mode}",
            flush=True,
        )
        if args.span_mode == "full":
            span_results, full_stateful, full_context = evaluate_full_span_pipeline(
                materialized_path=materialized_path,
                session_id=f"trace-{run_hash}",
                model_name=args.model,
            )
            _write_json(
                run_output / "span_pipeline.stateful_eval_result.json",
                full_stateful,
            )
            _write_json(
                run_output / "span_pipeline.trajectory_context.json",
                full_context,
            )
            span_usage = dict(full_stateful.get("token_usage") or {})
            _write_json(run_output / "span_pipeline.paper_v1.json", span_results)
        else:
            span_results = evaluate_span_context(
                context_path=context_path,
                stateful_result_path=stateful_result_path,
                model_name=args.model,
            )
            _assert_valid_results(span_results, arm="span context")
            span_usage = _usage(span_results, nested=True)
            _write_json(run_output / "span_context.paper_v1.json", span_results)

        record = {
            "hash": run_hash,
            "domain": item.get("domain"),
            "dataset": item.get("dataset"),
            "scenario": item.get("scenario"),
            "run_id": item.get("run_id"),
            "checker_present": item.get("checker_present"),
            "span_mode": args.span_mode,
            "transcript_chars": len(transcript),
            "traditional_results": traditional_results,
            "span_context_results": span_results,
            "traditional_usage": _usage(traditional_results, nested=False),
            "span_usage": span_usage,
        }
        _write_json(record_path, record)
        records.append(record)

    summary, disagreements = build_comparison_summary(
        records,
        input_per_million=args.input_cost_per_million,
        output_per_million=args.output_cost_per_million,
    )
    summary["model"] = args.model
    summary["span_mode"] = args.span_mode
    summary["methodology"] = {
        "span_context": (
            (
                "sequential Gemini span judgments, accumulated trajectory "
                "context, then shared paper_v1 audit"
            )
            if args.span_mode == "full"
            else (
                "paper_v1 metrics over persisted span-derived trajectory "
                "context; shared batch plus dedicated Delegation Accuracy call"
            )
        ),
        "traditional_deepeval": (
            "13 independent strict GEval judges over one deterministic whole-"
            "trajectory transcript; no fact, intent, or claim accumulation"
        ),
    }
    _write_json(output_dir / "agreement_summary.json", summary)
    _write_json(output_dir / "disagreements.json", disagreements)
    _write_disagreements(output_dir / "disagreements.csv", disagreements)
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
