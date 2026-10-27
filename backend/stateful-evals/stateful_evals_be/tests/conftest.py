#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Keep the tests off the network: the price table is not refreshed from LiteLLM."""

import pytest

from stateful_evals_be.evaluation import cost_estimator


@pytest.fixture(autouse=True)
def packaged_price_table(monkeypatch):
    monkeypatch.setenv("MODEL_PRICES_REFRESH", "false")
    monkeypatch.setattr(cost_estimator, "_lookup", None)
    monkeypatch.setattr(cost_estimator, "_next_refresh", 0.0)
