#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import logging
import math
import os
import re
from dataclasses import dataclass
from typing import Any
from mce.core.helpers import _conversation_text, _query_response
from mce.core.metric import Metric

logger = logging.getLogger(__name__)


def llm_binary_score(metric: Metric, prompt: str) -> tuple[float, str]:
    """Get a binary score from an LLM response using the first numeric token."""
    response = metric.call_llm(prompt).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", response)
    score = float(match.group()) if match else 0.0
    score = max(0.0, min(1.0, score))
    return score, response


class JudgeScoreError(ValueError):
    """The judge's reply had no usable score; the metric is reported as failed."""


@dataclass(frozen=True)
class JudgeSettings:
    """How a judge metric samples the LLM. Read from the environment per call.

    ``MCE_JUDGE_SAMPLES`` (default 1): judge calls per metric, averaged.
    ``MCE_JUDGE_TEMPERATURE`` (default 0.0 for one sample, else 0.7).
    ``MCE_JUDGE_LOGPROBS`` (default on): ask for token log-probabilities and, when the
    endpoint returns them, report the expected score over the score digits
    instead of the single digit the model sampled. Endpoints that reject the
    option are detected and the option is dropped for them.
    """

    samples: int = 1
    temperature: float = 0.0
    logprobs: bool = True
    top_logprobs: int = 5


def judge_settings() -> JudgeSettings:
    try:
        samples = max(1, int(os.getenv("MCE_JUDGE_SAMPLES", "1")))
    except ValueError:
        samples = 1
    try:
        temperature = float(
            os.getenv("MCE_JUDGE_TEMPERATURE", "0.0" if samples == 1 else "0.7")
        )
    except ValueError:
        temperature = 0.0 if samples == 1 else 0.7
    logprobs = os.getenv("MCE_JUDGE_LOGPROBS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    return JudgeSettings(samples=samples, temperature=temperature, logprobs=logprobs)


_SCORE_RE = re.compile(r"(?:score|rating)[^0-9\n]{0,8}(\d+(?:\.\d+)?)", re.IGNORECASE)


_BARE_NUMBER_RE = re.compile(r"\s*\**(\d+(?:\.\d+)?)\**\s*")


def parse_score(response: str) -> float:
    """The number after the last ``Score:`` / ``Rating:`` label in ``response``.

    Tolerates markdown around the number (``Score: **4**``) and accepts a reply
    that is only a number. Any other reply raises
    :class:`JudgeScoreError`, rather than guessing a number out of prose.
    """
    matches = _SCORE_RE.findall(response)
    if matches:
        return float(matches[-1])
    bare = _BARE_NUMBER_RE.fullmatch(response)
    if bare:
        return float(bare.group(1))
    raise JudgeScoreError("The judge reply contains no 'Score:' value")


def expected_score_from_logprobs(
    logprobs: list[dict[str, Any]], raw_score: float, scale: int
) -> float | None:
    """Expected score over the score-digit alternatives the model considered.

    Finds the generated score digit (the last token equal to ``raw_score`` that
    follows a ``score``/``rating`` label), takes the probabilities of the digit
    tokens ``1..scale`` among its top alternatives, normalizes them and returns
    their expectation. ``None`` when the score token cannot be located.
    """
    target = str(int(round(raw_score)))
    for index in range(len(logprobs) - 1, -1, -1):
        entry = logprobs[index]
        if str(entry.get("token", "")).strip() != target:
            continue
        context = "".join(
            t.get("token", "") for t in logprobs[max(0, index - 6) : index]
        )
        if not re.search(r"score|rating", context, re.IGNORECASE):
            continue
        digits = {str(d) for d in range(1, scale + 1)}
        best: dict[str, float] = {}
        for alt in (*entry.get("top", []), entry):
            token = str(alt.get("token", "")).strip()
            if token in digits:
                best[token] = max(best.get(token, -math.inf), alt["logprob"])
        if not best:
            return None
        weights = {digit: math.exp(lp) for digit, lp in best.items()}
        total = sum(weights.values())
        return sum(int(digit) * w for digit, w in weights.items()) / total
    return None


def _judge(metric: Metric, prompt: str, scale: int) -> tuple[float, str]:
    """Mean judge score in ``[1, scale]`` and the first reply, as reasoning."""
    settings = judge_settings()
    scores: list[float] = []
    reasoning: str | None = None
    failure: JudgeScoreError | None = None
    for sample in range(settings.samples):
        kwargs: dict[str, Any] = {"temperature": settings.temperature}
        if settings.logprobs:
            kwargs.update(logprobs=True, top_logprobs=settings.top_logprobs)
        if sample:
            kwargs["sample"] = sample
        metric.pop_completion()
        response = metric.call_llm(prompt, **kwargs).strip()
        completion = metric.pop_completion()
        try:
            raw = max(1.0, min(float(scale), parse_score(response)))
        except JudgeScoreError as exc:
            failure = exc
            logger.warning(
                "%s: judge sample %d unusable: %s", metric.metric_id, sample, exc
            )
            continue
        logprobs = getattr(completion, "logprobs", None)
        expected = (
            expected_score_from_logprobs(logprobs, raw, scale)
            if isinstance(logprobs, list)
            else None
        )
        scores.append(expected if expected is not None else raw)
        if reasoning is None:
            reasoning = response
    if not scores:
        raise failure or JudgeScoreError("The judge returned no score")
    return sum(scores) / len(scores), reasoning or ""


def llm_g_eval_score(
    metric: Metric, prompt: str, scale: int = 5
) -> tuple[float, str, float]:
    """G-Eval-style scoring.

    Calls the LLM with a CoT prompt that ends with ``Score: <1-N>``.
    Returns ``(normalized_score, reasoning, raw_score)`` where
    ``normalized_score = (raw - 1) / (scale - 1)`` in ``[0.0, 1.0]``.

    The score is continuous, not one of ``scale`` steps: it is the expected
    score over the model's score-digit probabilities when the endpoint returns
    log-probabilities, and the mean over ``MCE_JUDGE_SAMPLES`` calls. Raises
    :class:`JudgeScoreError` if no call produced a score.
    """
    raw_score, reasoning = _judge(metric, prompt, scale)
    normalized = (raw_score - 1.0) / (scale - 1.0)
    return normalized, reasoning, raw_score


def llm_cot_score(metric: Metric, prompt: str) -> tuple[float, str]:
    """One judge call; the number after ``Score:``/``Rating:`` and the reply.

    Raises :class:`JudgeScoreError` when the reply has no such number.
    """
    response = metric.call_llm(prompt).strip()
    return parse_score(response), response


def extract_conversation_text(context: dict) -> str:
    """Extract conversation text from context with fallback."""
    return _conversation_text(context)


def extract_query_response(context: dict) -> tuple[str, str]:
    """Extract query and response from context."""
    query, response = _query_response(context)
    return str(query), str(response)
