#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Combined per-span judging, prompt preparation and response parsing."""

import json
import re
from collections.abc import Callable
from typing import Any, Dict, List, Optional

from stateful_evals_be.evaluation.span_normalization import SpanNormalizer
from stateful_evals_be.models.requests import TemporalMetricOptions

_SPAN_STATE_DELTA_SYSTEM_PROMPT = """\
You evaluate one transition in an accumulated agent trajectory. Judge every
requested primitive from the same compact current-span delta and prior state.

Groundedness: pass when material output claims are supported by provided facts,
policy, or clearly marked uncertainty; fail fabricated or contradicted claims.
IntentRecognition: pass when the transition correctly recognizes and advances
the active user/delegated intent; fail missed, distorted, or abandoned intent.
Relevancy: pass when the transition is relevant and logically compatible with
the active intent and prior claims; fail material contradiction or non-progress.

Return strict JSON only with a `metrics` array. Each item must contain the exact
requested `metric_name`, binary numeric `score`, and one concise `reasoning`.
Optionally include a compact `state_delta` object with new claims, intent status
updates, and evidence links. Do not restate the supplied context.
"""


class SpanJudge:
    """Judge one transition using the caller-owned model query function."""

    def __init__(
        self,
        *,
        query: Callable[..., Any],
        options: TemporalMetricOptions,
        metric_names: list[str],
    ) -> None:
        self._query = query
        self.options = options
        self.metric_names = list(metric_names)

    @staticmethod
    def compact_value(value: Any, max_chars: int) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            text = " ".join(value.split())
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except Exception:
                text = str(value)
        if len(text) <= max_chars:
            if not isinstance(value, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass
            return text
        return text[: max_chars - 22] + "... [truncated]"

    def prepare_span(self, span_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Keep only current-turn I/O; never forward accumulated prompt history."""
        input_payload = span_dict.get("input_payload")
        output_payload = span_dict.get("output_payload")
        messages: List[Dict[str, str]] = []

        if isinstance(input_payload, dict):
            indexed: Dict[int, Dict[str, str]] = {}
            role_re = re.compile(r"^gen_ai\.prompt\.(\d+)\.role$")
            content_re = re.compile(r"^gen_ai\.prompt\.(\d+)\.content$")
            for key, value in input_payload.items():
                match = role_re.match(str(key))
                if match:
                    indexed.setdefault(int(match.group(1)), {})["role"] = str(value)
                    continue
                match = content_re.match(str(key))
                if match:
                    indexed.setdefault(int(match.group(1)), {})["content"] = (
                        SpanNormalizer._normalize_text(value)
                    )
            messages = [
                {
                    "role": entry.get("role", "user").lower(),
                    "content": str(entry.get("content", ""))[:1600],
                }
                for _, entry in sorted(indexed.items())
                if entry.get("content")
                and entry.get("role", "user").lower() != "system"
            ]

        if not messages:
            for message_list in SpanNormalizer._iter_message_lists(input_payload):
                for message in message_list:
                    parsed = SpanNormalizer._extract_message_entry(message)
                    if parsed and parsed["role"] != "system":
                        parsed["content"] = parsed["content"][:1600]
                        messages.append(parsed)

        max_messages = int(self.options.max_messages or 2)
        current_input: Any = messages[-max_messages:]
        if not current_input:
            current_input = self.compact_value(input_payload, 2400)

        output_texts: List[str] = []
        if isinstance(output_payload, dict):
            completion_re = re.compile(r"^gen_ai\.completion\.(\d+)\.content$")
            indexed_output = sorted(
                (
                    int(match.group(1)),
                    SpanNormalizer._normalize_text(value),
                )
                for key, value in output_payload.items()
                if (match := completion_re.match(str(key)))
            )
            output_texts = [text[:2400] for _, text in indexed_output if text]
        current_output: Any = output_texts[-1] if output_texts else None
        if current_output is None:
            current_output = self.compact_value(output_payload, 3000)

        return {
            "span_id": span_dict.get("span_id", ""),
            "entity_type": span_dict.get("entity_type", ""),
            "entity_name": span_dict.get("entity_name", ""),
            "contains_error": bool(span_dict.get("contains_error")),
            "current_input": current_input,
            "current_output": current_output,
        }

    def evaluate(
        self,
        span_dict: Dict[str, Any],
        *,
        context_state: Dict[str, Any],
        policy: str = "",
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Judge all applicable span primitives in one bounded LLM call."""
        requested = metrics if metrics is not None else self.metric_names
        prompt_payload = {
            "requested_metrics": requested,
            "current_span_delta": self.prepare_span(span_dict),
            "trajectory_state_before_span": context_state,
            "policy": policy[:5000],
            "output_schema": {
                "metrics": [
                    {
                        "metric_name": "exact requested metric name",
                        "score": "integer 0 or 1",
                        "reasoning": "concise context-grounded explanation",
                    }
                ],
                "state_delta": {
                    "claims": [],
                    "intent_updates": [],
                    "evidence_links": [],
                },
            },
        }
        results_by_name: Dict[str, Dict[str, Any]] = {}
        state_delta: Dict[str, Any] = {}
        usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        parse_error: Exception | None = None

        def collect_metrics(
            parsed: Dict[str, Any],
            expected: List[str],
        ) -> None:
            raw_metrics = parsed.get("metrics")
            if isinstance(raw_metrics, dict):
                raw_metrics = [
                    {
                        "metric_name": name,
                        **(item if isinstance(item, dict) else {}),
                    }
                    for name, item in raw_metrics.items()
                ]
            if not isinstance(raw_metrics, list):
                raw_metrics = [parsed] if parsed.get("metric_name") else []

            by_name = {
                str(item.get("metric_name") or ""): item
                for item in raw_metrics
                if isinstance(item, dict)
            }
            by_short_name = {
                name.split(".")[-1]: item for name, item in by_name.items()
            }
            by_normalized_name = {
                re.sub(r"[^a-z0-9]", "", name.split(".")[-1].casefold()): item
                for name, item in by_name.items()
            }
            for metric_name in expected:
                normalized_name = re.sub(
                    r"[^a-z0-9]",
                    "",
                    metric_name.split(".")[-1].casefold(),
                )
                item = (
                    by_name.get(metric_name)
                    or by_short_name.get(metric_name.split(".")[-1])
                    or by_normalized_name.get(normalized_name)
                )
                if item is None:
                    continue
                raw_score = item.get("score", item.get("value"))
                if isinstance(raw_score, str):
                    normalized_score = raw_score.strip().casefold()
                    if normalized_score in {"pass", "passed", "true"}:
                        raw_score = 1
                    elif normalized_score in {"fail", "failed", "false"}:
                        raw_score = 0
                try:
                    score = float(raw_score)
                except (TypeError, ValueError):
                    continue
                if score not in {0.0, 1.0}:
                    continue
                results_by_name[metric_name] = {
                    "metric_name": metric_name,
                    "value": score,
                    "reasoning": str(item.get("reasoning") or ""),
                    "success": True,
                }

        def add_usage(response: Any) -> None:
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(
                getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
            )
            usage_totals["prompt_tokens"] += prompt_tokens
            usage_totals["completion_tokens"] += completion_tokens
            usage_totals["total_tokens"] += total_tokens

        max_attempts = self.options.span_judge_max_attempts
        for attempt in range(max_attempts):
            missing = [
                metric_name
                for metric_name in requested
                if metric_name not in results_by_name
            ]
            attempt_payload = {
                **prompt_payload,
                "requested_metrics": missing,
            }
            messages = [
                {"role": "system", "content": _SPAN_STATE_DELTA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        attempt_payload,
                        ensure_ascii=True,
                        default=str,
                    ),
                },
            ]
            if attempt:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous response omitted or invalidated the "
                            f"remaining requested metrics: {missing}. Return strict "
                            "compact JSON for only these metrics, with one score "
                            "of 0 or 1 for each. Do not omit a metric."
                        ),
                    }
                )
            response = self._query(
                messages,
                max_tokens=min(
                    8192,
                    self.options.span_judge_max_tokens * (2**attempt),
                ),
            )
            add_usage(response)

            content = (response.choices[0].message.content or "").strip()
            try:
                parsed = self.parse_response(content)
            except (json.JSONDecodeError, ValueError) as exc:
                parse_error = exc
                continue
            candidate_delta = parsed.get("state_delta")
            if isinstance(candidate_delta, dict) and candidate_delta:
                state_delta = candidate_delta
            collect_metrics(parsed, missing)
            if len(results_by_name) == len(requested):
                break

        remaining = [
            metric_name
            for metric_name in requested
            if metric_name not in results_by_name
        ]
        for metric_name in remaining:
            single_payload = {
                **prompt_payload,
                "requested_metrics": [metric_name],
                "output_schema": {
                    "metrics": [
                        {
                            "metric_name": metric_name,
                            "score": "integer 0 or 1",
                            "reasoning": "one concise sentence",
                        }
                    ]
                },
            }
            messages = [
                {"role": "system", "content": _SPAN_STATE_DELTA_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        single_payload,
                        ensure_ascii=True,
                        default=str,
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Return exactly one result for {metric_name}. "
                        "Use a binary numeric score of 0 or 1."
                    ),
                },
            ]
            response = self._query(
                messages,
                max_tokens=self.options.span_judge_max_tokens,
            )
            add_usage(response)
            content = (response.choices[0].message.content or "").strip()
            try:
                parsed = self.parse_response(content)
            except (json.JSONDecodeError, ValueError) as exc:
                parse_error = exc
                continue
            collect_metrics(parsed, [metric_name])

        results = [
            results_by_name[metric_name]
            for metric_name in requested
            if metric_name in results_by_name
        ]
        failed = [
            {
                "metric_name": metric_name,
                "error_message": (
                    "Combined judge omitted requested metric after "
                    f"{max_attempts} attempt(s)"
                    + (f": {parse_error}" if parse_error else "")
                ),
            }
            for metric_name in requested
            if metric_name not in results_by_name
        ]
        return {
            "span_id": span_dict.get("span_id", ""),
            "entity_type": span_dict.get("entity_type", ""),
            "entity_name": span_dict.get("entity_name", ""),
            "results": results,
            "failed_metrics": failed,
            "state_delta": state_delta,
            "usage": usage_totals,
        }

    @staticmethod
    def parse_response(raw_text: str) -> Dict[str, Any]:
        """Parse a JSON object even when a provider prefixes brief reasoning."""
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                parsed, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise json.JSONDecodeError("No JSON object found", text, 0)
