#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Estimate the USD cost of LLM calls from token counts and a price table.

The table is LiteLLM's price list (input/output cost per token and aliases per
model). It starts as ``data/model_prices.json``, a trimmed copy packaged with the
library and refreshed from LiteLLM whenever the image is built. Unless
``MODEL_PRICES_REFRESH`` is ``false``, it is then refreshed at run time from
``MODEL_PRICES_URL`` (LiteLLM's published file) at the first price lookup and
again every ``MODEL_PRICES_TTL_SECONDS`` (a day). If LiteLLM cannot be reached or
its file is invalid, the table already in use stays, packaged or last fetched,
and the fetch is retried an hour later.

A model with no entry is priced like ``gpt-4o``, so a cost is always an
estimate, never a billed amount.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PRICE_FILE = Path(__file__).resolve().parent / "data" / "model_prices.json"
DEFAULT_PRICING_MODEL = "gpt-4o"
_DEFAULT_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
_DEFAULT_TTL_SECONDS = 24 * 3600
_RETRY_SECONDS = 3600
_FETCH_TIMEOUT_SECONDS = 5
_MIN_MODELS = 1000  # a download with fewer entries is almost certainly broken

# model name -> (input cost per token, output cost per token)
_Price = tuple[float, float]

_lock = threading.Lock()
_table: dict[str, _Price] | None = None
_next_refresh = 0.0  # time.monotonic() of the next run-time refresh


def _parse(raw: Any) -> dict[str, _Price]:
    """Price by name and alias of every model with both per-token costs."""
    table: dict[str, _Price] = {}
    if not isinstance(raw, dict):
        return table
    for name, meta in raw.items():
        if not isinstance(meta, dict):
            continue
        try:
            price = (
                float(meta["input_cost_per_token"]),
                float(meta["output_cost_per_token"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        aliases = [a for a in meta.get("aliases") or () if isinstance(a, str)]
        for alias in (name, *aliases):
            table[alias.strip().lower()] = price
    return table


def _packaged_table() -> dict[str, _Price]:
    try:
        return _parse(json.loads(_PRICE_FILE.read_text(encoding="utf-8")))
    except Exception:
        logger.exception("Unable to load model price table: %s", _PRICE_FILE)
        return {}


def _fetched_table(url: str) -> dict[str, _Price]:
    """The table at ``url``; raises ``ValueError`` unless it looks like LiteLLM's."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "oxp-mce-model-prices"}
    )
    with urllib.request.urlopen(request, timeout=_FETCH_TIMEOUT_SECONDS) as response:
        table = _parse(json.loads(response.read().decode("utf-8")))
    if len(table) < _MIN_MODELS or DEFAULT_PRICING_MODEL not in table:
        raise ValueError(f"the price file looks broken ({len(table)} priced names)")
    return table


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


def _price_table() -> dict[str, _Price]:
    global _table, _next_refresh
    with _lock:
        if _table is None:
            _table = _packaged_table()
        if _refresh_enabled() and time.monotonic() >= _next_refresh:
            url = os.getenv("MODEL_PRICES_URL", _DEFAULT_URL)
            try:
                _table = _fetched_table(url)
                _next_refresh = time.monotonic() + _ttl_seconds()
                logger.info("Refreshed %d model prices from %s", len(_table), url)
            except Exception as exc:
                _next_refresh = time.monotonic() + _RETRY_SECONDS
                logger.warning(
                    "Could not refresh model prices from %s (%s); using the table already loaded",
                    url,
                    exc,
                )
        return _table


def resolve_model_price(model: str) -> _Price | None:
    """Price of ``model`` by exact name or alias, also without a provider prefix."""
    table = _price_table()
    key = (model or "").strip().lower()
    for candidate in (key, key.rsplit("/", 1)[-1]):
        if candidate in table:
            return table[candidate]
    return None


def estimate_cost_usd(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float | None:
    """Estimated USD cost, or ``None`` when no price (not even the default) exists."""
    price = resolve_model_price(model)
    if price is None:
        price = resolve_model_price(DEFAULT_PRICING_MODEL)
        if price is None:
            return None
        logger.debug(
            "No price for model %r; using %r pricing", model, DEFAULT_PRICING_MODEL
        )
    return round(prompt_tokens * price[0] + completion_tokens * price[1], 8)
