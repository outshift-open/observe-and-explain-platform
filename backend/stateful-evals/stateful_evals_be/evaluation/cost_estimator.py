#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Local LLM token cost estimation for stateful eval runs."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from stateful_evals_be.models.requests import TokenCostEstimate

logger = logging.getLogger("stateful_evals_be.cost_estimator")

_PRICE_FILE = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "model_prices_and_context_window.json"
)
_DEFAULT_PRICING_MODEL = "gpt-4o"


@dataclass(frozen=True)
class ModelPrice:
    model_name: str
    input_cost_per_token: float
    output_cost_per_token: float
    source: str

    @property
    def input_cost_per_1m_tokens(self) -> float:
        return self.input_cost_per_token * 1_000_000

    @property
    def output_cost_per_1m_tokens(self) -> float:
        return self.output_cost_per_token * 1_000_000


def estimate_token_cost(
    token_usage: Any,
    model_name: str,
) -> TokenCostEstimate:
    """Estimate token cost using the vendored LiteLLM-style pricing JSON."""

    warnings: List[str] = []
    price = resolve_model_price(model_name)

    if price is None:
        price = resolve_model_price(_DEFAULT_PRICING_MODEL)
        warnings.append(
            f"No local pricing found for model {model_name!r}; "
            f"used {_DEFAULT_PRICING_MODEL!r} pricing as the default."
        )

    if price is None:
        warnings.append(
            f"No local pricing found for default model {_DEFAULT_PRICING_MODEL!r}; "
            "cost set to 0."
        )
        return TokenCostEstimate(
            model_name=model_name,
            pricing_source="unavailable",
            warnings=warnings,
        )

    prompt_tokens = _int_attr(token_usage, "prompt_tokens")
    completion_tokens = _int_attr(token_usage, "completion_tokens")
    prompt_cost = prompt_tokens * price.input_cost_per_token
    completion_cost = completion_tokens * price.output_cost_per_token

    by_phase = {}
    for phase, prefix in (
        ("mce", "mce"),
        ("review", "review"),
        ("cross_span", "cross_span"),
        ("final_outcome", "final_outcome"),
        ("high_level", "high_level"),
    ):
        phase_prompt = _int_attr(token_usage, f"{prefix}_prompt_tokens")
        phase_completion = _int_attr(token_usage, f"{prefix}_completion_tokens")
        phase_cost = (
            phase_prompt * price.input_cost_per_token
            + phase_completion * price.output_cost_per_token
        )
        by_phase[phase] = {
            "prompt_tokens": phase_prompt,
            "completion_tokens": phase_completion,
            "estimated_cost_usd": _round_cost(phase_cost),
        }

    return TokenCostEstimate(
        model_name=model_name,
        pricing_model_name=price.model_name,
        pricing_source=price.source,
        input_cost_per_1m_tokens=round(price.input_cost_per_1m_tokens, 6),
        output_cost_per_1m_tokens=round(price.output_cost_per_1m_tokens, 6),
        prompt_cost_usd=_round_cost(prompt_cost),
        completion_cost_usd=_round_cost(completion_cost),
        estimated_cost_usd=_round_cost(prompt_cost + completion_cost),
        by_phase=by_phase,
        warnings=warnings,
    )


def resolve_model_price(model_name: str) -> Optional[ModelPrice]:
    lookup = _price_lookup()
    key = _normalize_name(model_name)
    if key in lookup:
        return lookup[key]

    # Keep the fallback intentionally simple: exact name or declared alias.
    # Provider-prefixed aliases like azure/gpt-4o are represented explicitly in
    # the vendored JSON.
    return None


@lru_cache(maxsize=1)
def _price_lookup() -> Dict[str, ModelPrice]:
    try:
        raw = json.loads(_PRICE_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Unable to load local model pricing file: %s", _PRICE_FILE)
        return {}

    if not isinstance(raw, dict):
        logger.warning("Local model pricing file is not a JSON object: %s", _PRICE_FILE)
        return {}

    lookup: Dict[str, ModelPrice] = {}
    for name, metadata in raw.items():
        if not isinstance(metadata, dict):
            continue
        pricing = _pricing_from_mapping(metadata)
        if pricing is None:
            continue
        price = ModelPrice(
            model_name=str(name),
            input_cost_per_token=pricing[0],
            output_cost_per_token=pricing[1],
            source="local_model_prices_json",
        )
        for alias in _names_and_aliases(str(name), metadata):
            lookup[_normalize_name(alias)] = price
    return lookup


def _names_and_aliases(name: str, metadata: Dict[str, Any]) -> Iterable[str]:
    yield name
    aliases = metadata.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str):
                yield alias


def _pricing_from_mapping(mapping: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    input_cost = _float_value(mapping, "input_cost_per_token")
    output_cost = _float_value(mapping, "output_cost_per_token")
    if input_cost is None or output_cost is None:
        return None
    return float(input_cost), float(output_cost)


def _float_value(mapping: Dict[str, Any], key: str) -> Optional[float]:
    value = mapping.get(key)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_name(model_name: str) -> str:
    return (model_name or "").strip().lower()


def _int_attr(obj: Any, key: str) -> int:
    if isinstance(obj, dict):
        value = obj.get(key, 0)
    else:
        value = getattr(obj, key, 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _round_cost(value: float) -> float:
    return round(float(value), 8)
