#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from mce.providers.sdk.metrics import DurationMetric, TokenCountMetric, CostMetric


def test_sdk_metrics():
    duration = DurationMetric()
    token_count = TokenCountMetric()
    cost = CostMetric()

    res_duration = duration.compute("span_1", {"duration_ms": 123.4})
    assert res_duration.value == 123.4

    res_tokens = token_count.compute(
        "span_2",
        {"prompt_tokens": 10, "completion_tokens": 5},
    )
    assert res_tokens.value == 15.0

    res_cost = cost.compute(
        "span_3",
        {"cost_per_token": 0.01, "total_tokens": 200},
    )
    assert res_cost.value == 2.0
