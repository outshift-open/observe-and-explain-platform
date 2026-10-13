#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LLM token cost estimation for stateful eval runs.

The price table is LiteLLM's. It starts as ``data/model_prices_and_context_window.json``,
the copy packaged with the library and refreshed from LiteLLM whenever the image
is built. Unless ``MODEL_PRICES_REFRESH`` is ``false``, it is then refreshed at
run time from ``MODEL_PRICES_URL`` (LiteLLM's published file) at the first price
lookup and again every ``MODEL_PRICES_TTL_SECONDS`` (a day). If LiteLLM cannot be
reached or its file is invalid, the table already in use stays, packaged or last
fetched, and the fetch is retried an hour later.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from dataclasses import dataclass
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
_DEFAULT_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
_DEFAULT_TTL_SECONDS = 24 * 3600
_RETRY_SECONDS = 3600
_FETCH_TIMEOUT_SECONDS = 5
_MIN_MODELS = 1000  # a download with fewer entries is almost certainly broken

_lock = threading.Lock()
_lookup: Dict[str, "ModelPrice"] | None = None
_next_refresh = 0.0  # time.monotonic() of the next run-time refresh


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


def estimate_usage_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str,
) -> float:
    """USD cost of a token count, falling back to the default pricing model."""

    price = resolve_model_price(model_name) or resolve_model_price(
        _DEFAULT_PRICING_MODEL
    )
    if price is None:
        return 0.0
    return _round_cost(
        prompt_tokens * price.input_cost_per_token
        + completion_tokens * price.output_cost_per_token
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


def _parse(raw: Any, source: str) -> Dict[str, ModelPrice]:
    """Price by name and alias of every model with both per-token costs."""
    lookup: Dict[str, ModelPrice] = {}
    if not isinstance(raw, dict):
        return lookup
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
            source=source,
        )
        for alias in _names_and_aliases(str(name), metadata):
            lookup[_normalize_name(alias)] = price
    return lookup


def _packaged_lookup() -> Dict[str, ModelPrice]:
    try:
        raw = json.loads(_PRICE_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Unable to load local model pricing file: %s", _PRICE_FILE)
        return {}
    if not isinstance(raw, dict):
        logger.warning("Local model pricing file is not a JSON object: %s", _PRICE_FILE)
        return {}
    return _parse(raw, "local_model_prices_json")


def _fetched_lookup(url: str) -> Dict[str, ModelPrice]:
    """The table at ``url``; raises ``ValueError`` unless it looks like LiteLLM's."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "oxp-stateful-evals-model-prices"}
    )
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        lookup = _parse(
            json.loads(response.read().decode("utf-8")), "litellm_model_prices_json"
        )
    if (
        len(lookup) < _MIN_MODELS
        or _normalize_name(_DEFAULT_PRICING_MODEL) not in lookup
    ):
        raise ValueError(f"the price file looks broken ({len(lookup)} priced names)")
    return lookup


def _refresh_enabled() -> bool:
    return os.getenv("MODEL_PRICES_REFRESH", "true").strip().lower() not in (
        "false",
        "0",
        "no",
    )


def _ttl_seconds() -> float:
    try:
        return float(os.getenv("MODEL_PRICES_TTL_SECONDS", _DEFAULT_TTL_SECONDS))
    except ValueError:
        return _DEFAULT_TTL_SECONDS


def _price_lookup() -> Dict[str, ModelPrice]:
    global _lookup, _next_refresh
    with _lock:
        if _lookup is None:
            _lookup = _packaged_lookup()
        if _refresh_enabled() and time.monotonic() >= _next_refresh:
            url = os.getenv("MODEL_PRICES_URL", _DEFAULT_URL)
            try:
                _lookup = _fetched_lookup(url)
                _next_refresh = time.monotonic() + _ttl_seconds()
                logger.info("Refreshed %d model prices from %s", len(_lookup), url)
            except Exception as exc:
                _next_refresh = time.monotonic() + _RETRY_SECONDS
                logger.warning(
                    "Could not refresh model prices from %s (%s); using the table already loaded",
                    url,
                    exc,
                )
        return _lookup


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
