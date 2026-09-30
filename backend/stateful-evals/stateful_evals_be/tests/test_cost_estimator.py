#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from stateful_evals_be.evaluation.cost_estimator import estimate_token_cost
from stateful_evals_be.models.requests import TokenUsage


def test_estimate_cost_from_local_proxy_alias() -> None:
    estimate = estimate_token_cost(
        TokenUsage(prompt_tokens=1_000, completion_tokens=2_000, total_tokens=3_000),
        "bedrock/global.anthropic.claude-opus-4-6-1",
    )

    assert estimate.pricing_source == "local_model_prices_json"
    assert estimate.pricing_model_name in {
        "bedrock/global.anthropic.claude-opus-4-6-1",
        "bedrock/global.anthropic.claude-opus-4-6-v1",
    }
    assert estimate.input_cost_per_1m_tokens == 5.0
    assert estimate.output_cost_per_1m_tokens == 25.0
    assert estimate.estimated_cost_usd == 0.055
    assert estimate.warnings == []


def test_estimate_cost_for_current_openai_model_from_local_json() -> None:
    estimate = estimate_token_cost(
        TokenUsage(
            prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000
        ),
        "gpt-5.4-mini",
    )

    assert estimate.pricing_source == "local_model_prices_json"
    assert estimate.pricing_model_name == "gpt-5.4-mini"
    assert estimate.input_cost_per_1m_tokens == 0.75
    assert estimate.output_cost_per_1m_tokens == 4.5
    assert estimate.estimated_cost_usd == 5.25


def test_unknown_model_uses_gpt4o_default_pricing() -> None:
    estimate = estimate_token_cost(
        TokenUsage(
            prompt_tokens=1_000_000, completion_tokens=1_000_000, total_tokens=2_000_000
        ),
        "unknown/private-model",
    )

    assert estimate.pricing_source == "local_model_prices_json"
    assert estimate.pricing_model_name == "gpt-4o"
    assert estimate.input_cost_per_1m_tokens == 2.5
    assert estimate.output_cost_per_1m_tokens == 10.0
    assert estimate.estimated_cost_usd == 12.5
    assert "used 'gpt-4o' pricing" in estimate.warnings[0]


def test_high_level_shared_batch_is_reported_as_one_cost_phase() -> None:
    estimate = estimate_token_cost(
        TokenUsage(
            prompt_tokens=1_000,
            completion_tokens=200,
            total_tokens=1_200,
            high_level_prompt_tokens=1_000,
            high_level_completion_tokens=200,
            high_level_total_tokens=1_200,
        ),
        "gpt-4o",
    )

    assert estimate.by_phase["high_level"]["prompt_tokens"] == 1_000
    assert estimate.by_phase["high_level"]["completion_tokens"] == 200
