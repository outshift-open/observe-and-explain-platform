#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import re
from mce.core.helpers import _conversation_text, _query_response
from mce.core.metric import Metric


def llm_binary_score(metric: Metric, prompt: str) -> tuple[float, str]:
    """Get a binary score from an LLM response using the first numeric token."""
    response = metric.call_llm(prompt).strip()
    match = re.search(r"-?\d+(?:\.\d+)?", response)
    score = float(match.group()) if match else 0.0
    score = max(0.0, min(1.0, score))
    return score, response


def llm_g_eval_score(
    metric: Metric, prompt: str, scale: int = 5
) -> tuple[float, str, float]:
    """G-Eval-style scoring.

    Calls the LLM with a CoT prompt that ends with ``Score: <1-N>``.
    Returns ``(normalized_score, reasoning, raw_score)`` where
    ``normalized_score = (raw - 1) / (scale - 1)`` in ``[0.0, 1.0]``.
    """
    raw_score, reasoning = llm_cot_score(metric, prompt)
    raw_score = max(1.0, min(float(scale), raw_score))
    normalized = (raw_score - 1.0) / (scale - 1.0)
    return normalized, reasoning, raw_score


def llm_cot_score(metric: Metric, prompt: str) -> tuple[float, str]:
    """
    Get a score from an LLM response using Chain-of-Thought.
    Expects response in format:
    Reasoning: ...
    Score: <number>
    """
    response = metric.call_llm(prompt).strip()

    # Try to extract score from the end
    score_match = re.search(
        r"(?:Score|Rating):\s*(\d+(?:\.\d+)?)", response, re.IGNORECASE
    )
    if not score_match:
        # Fallback to last number in text
        all_nums = re.findall(r"\d+(?:\.\d+)?", response)
        if all_nums:
            score = float(all_nums[-1])
        else:
            score = 0.0
    else:
        score = float(score_match.group(1))

    # Normalize if needed (assuming 0-1 or 1-5, handled by caller or prompt instructions)
    # But usually G-Eval is 1-5. Let's return raw for now and let metric normalize.

    return score, response


def extract_conversation_text(context: dict) -> str:
    """Extract conversation text from context with fallback."""
    return _conversation_text(context)


def extract_query_response(context: dict) -> tuple[str, str]:
    """Extract query and response from context."""
    query, response = _query_response(context)
    return str(query), str(response)
