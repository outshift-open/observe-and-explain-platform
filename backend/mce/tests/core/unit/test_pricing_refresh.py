#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Run-time refresh of the price table from LiteLLM, with the packaged file as fallback."""

import io
import json

import pytest

from mce.engine import pricing


def _litellm_table(gpt4o_input: float) -> dict:
    table = {
        f"model-{i}": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}
        for i in range(pricing._MIN_MODELS)
    }
    table["gpt-4o"] = {
        "input_cost_per_token": gpt4o_input,
        "output_cost_per_token": 4 * gpt4o_input,
        "aliases": ["gpt-4o-latest"],
    }
    table["sample_spec"] = {"max_tokens": "see docs"}
    return table


class _Upstream:
    """Stands in for LiteLLM's file: answers urlopen and counts the requests."""

    def __init__(self, monkeypatch, payload):
        self.payload = payload
        self.requests = 0
        monkeypatch.setattr(pricing.urllib.request, "urlopen", self._urlopen)

    def _urlopen(self, request, timeout):
        self.requests += 1
        if isinstance(self.payload, Exception):
            raise self.payload
        return io.BytesIO(json.dumps(self.payload).encode())


@pytest.fixture
def refreshing(monkeypatch):
    monkeypatch.setenv("MODEL_PRICES_REFRESH", "true")
    clock = {"now": 1000.0}
    monkeypatch.setattr(pricing.time, "monotonic", lambda: clock["now"])
    return clock


def test_a_refresh_replaces_the_packaged_prices(monkeypatch, refreshing):
    upstream = _Upstream(monkeypatch, _litellm_table(gpt4o_input=7e-6))

    assert pricing.resolve_model_price("gpt-4o") == (7e-6, 2.8e-5)
    assert pricing.resolve_model_price("gpt-4o-latest") == (7e-6, 2.8e-5)
    assert pricing.resolve_model_price("sample_spec") is None
    assert upstream.requests == 1


def test_the_table_is_fetched_once_per_ttl(monkeypatch, refreshing):
    monkeypatch.setenv("MODEL_PRICES_TTL_SECONDS", "600")
    upstream = _Upstream(monkeypatch, _litellm_table(gpt4o_input=7e-6))

    pricing.resolve_model_price("gpt-4o")
    refreshing["now"] += 599
    pricing.resolve_model_price("gpt-4o")
    assert upstream.requests == 1

    upstream.payload = _litellm_table(gpt4o_input=9e-6)
    refreshing["now"] += 2
    assert pricing.resolve_model_price("gpt-4o") == (9e-6, 3.6e-5)
    assert upstream.requests == 2


def test_the_packaged_table_is_used_when_litellm_is_unreachable(
    monkeypatch, refreshing
):
    upstream = _Upstream(monkeypatch, OSError("no route to host"))

    assert pricing.resolve_model_price("gpt-4o") is not None
    assert pricing.resolve_model_price("gpt-4o") == pricing._packaged_table()["gpt-4o"]
    assert upstream.requests == 1


def test_a_failed_refresh_is_retried_after_an_hour_not_on_every_lookup(
    monkeypatch, refreshing
):
    upstream = _Upstream(monkeypatch, OSError("down"))

    pricing.resolve_model_price("gpt-4o")
    refreshing["now"] += 3599
    pricing.resolve_model_price("gpt-4o")
    assert upstream.requests == 1

    upstream.payload = _litellm_table(gpt4o_input=7e-6)
    refreshing["now"] += 2
    assert pricing.resolve_model_price("gpt-4o") == (7e-6, 2.8e-5)
    assert upstream.requests == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"gpt-4o": {"input_cost_per_token": 1, "output_cost_per_token": 1}},
        ["not", "a", "table"],
        {
            f"model-{i}": {"input_cost_per_token": 1e-6, "output_cost_per_token": 2e-6}
            for i in range(pricing._MIN_MODELS)
        },
    ],
    ids=["too few models", "not an object", "no gpt-4o"],
)
def test_an_invalid_file_keeps_the_packaged_table(monkeypatch, refreshing, payload):
    _Upstream(monkeypatch, payload)

    assert pricing.resolve_model_price("gpt-4o") == pricing._packaged_table()["gpt-4o"]


def test_a_failed_refresh_keeps_the_last_fetched_table(monkeypatch, refreshing):
    monkeypatch.setenv("MODEL_PRICES_TTL_SECONDS", "60")
    upstream = _Upstream(monkeypatch, _litellm_table(gpt4o_input=7e-6))
    pricing.resolve_model_price("gpt-4o")

    upstream.payload = OSError("down")
    refreshing["now"] += 61

    assert pricing.resolve_model_price("gpt-4o") == (7e-6, 2.8e-5)


@pytest.mark.parametrize("flag", ["false", "0", "no"])
def test_refresh_can_be_switched_off(monkeypatch, refreshing, flag):
    monkeypatch.setenv("MODEL_PRICES_REFRESH", flag)
    upstream = _Upstream(monkeypatch, _litellm_table(gpt4o_input=7e-6))

    assert pricing.resolve_model_price("gpt-4o") == pricing._packaged_table()["gpt-4o"]
    assert upstream.requests == 0


def test_the_source_url_can_be_overridden(monkeypatch, refreshing):
    monkeypatch.setenv("MODEL_PRICES_URL", "http://prices.internal/litellm.json")
    seen = []
    payload = _litellm_table(gpt4o_input=7e-6)

    def urlopen(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(pricing.urllib.request, "urlopen", urlopen)

    pricing.resolve_model_price("gpt-4o")

    assert seen == ["http://prices.internal/litellm.json"]
