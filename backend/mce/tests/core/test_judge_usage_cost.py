#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Judge token usage and estimated cost: capture, accounting and the error paths."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from mce.core.metric import MetricResult
from mce.engine.llm import CompletionResult, LLMService
from mce.engine.pricing import estimate_cost_usd, resolve_model_price
from mce.engine.usage import JudgeUsage, record_usage, track_usage


@pytest.fixture(autouse=True)
def reset_singleton():
    LLMService._instance = None
    yield
    LLMService._instance = None


# ---------------------------------------------------------------- pricing


class TestPricing:
    def test_cost_from_tokens_and_list_price(self):
        # gpt-4o: $2.50 / 1M input, $10 / 1M output
        assert estimate_cost_usd("gpt-4o", 1000, 500) == pytest.approx(0.0075)

    def test_provider_prefix_is_ignored(self):
        assert estimate_cost_usd("azure/gpt-4o", 1000, 500) == estimate_cost_usd(
            "gpt-4o", 1000, 500
        )

    def test_lookup_is_case_insensitive(self):
        assert resolve_model_price("GPT-4o") == resolve_model_price("gpt-4o")

    def test_unknown_model_is_priced_like_gpt_4o(self):
        assert estimate_cost_usd("not-a-real-model", 1000, 500) == estimate_cost_usd(
            "gpt-4o", 1000, 500
        )

    def test_no_tokens_cost_nothing(self):
        assert estimate_cost_usd("gpt-4o", 0, 0) == 0.0


# ---------------------------------------------------------------- usage scope


class TestUsageScope:
    def test_records_calls_inside_the_scope(self):
        with track_usage() as usage:
            record_usage("gpt-4o", 100, 20)
            record_usage("gpt-4o", 50, 10)
        assert (
            usage.prompt_tokens,
            usage.completion_tokens,
            usage.total_tokens,
            usage.calls,
        ) == (150, 30, 180, 2)

    def test_calls_outside_a_scope_are_ignored(self):
        record_usage("gpt-4o", 100, 20)  # must not raise

    def test_scopes_do_not_leak_into_each_other(self):
        with track_usage() as first:
            record_usage("gpt-4o", 10, 1)
        with track_usage() as second:
            record_usage("gpt-4o", 20, 2)
        assert (first.prompt_tokens, second.prompt_tokens) == (10, 20)

    def test_worker_threads_count_only_when_given_the_context(self):
        import contextvars

        def work():
            record_usage("gpt-4o", 5, 1)

        with track_usage() as usage:
            plain = threading.Thread(target=work)
            plain.start()
            plain.join()
            assert usage.calls == 0  # a bare thread does not inherit the scope
            ctx = contextvars.copy_context()
            copied = threading.Thread(target=ctx.run, args=(work,))
            copied.start()
            copied.join()
        assert usage.calls == 1

    def test_concurrent_adds_are_exact(self):
        usage = JudgeUsage()
        threads = [
            threading.Thread(target=lambda: [usage.add("m", 1, 1) for _ in range(500)])
            for _ in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert (usage.prompt_tokens, usage.completion_tokens, usage.calls) == (
            4000,
            4000,
            4000,
        )

    def test_metadata_has_tokens_model_and_cost(self):
        usage = JudgeUsage()
        usage.add("gpt-4o", 1000, 500)
        assert usage.to_metadata() == {
            "evaluation_model": "gpt-4o",
            "evaluation_prompt_tokens": 1000,
            "evaluation_completion_tokens": 500,
            "evaluation_total_tokens": 1500,
            "evaluation_cost_usd": pytest.approx(0.0075),
        }

    def test_no_calls_means_no_metadata(self):
        assert JudgeUsage().to_metadata() == {}

    def test_several_models_report_tokens_but_no_single_cost(self):
        usage = JudgeUsage()
        usage.add("gpt-4o", 100, 10)
        usage.add("gpt-4o-mini", 100, 10)
        metadata = usage.to_metadata()
        assert metadata["evaluation_model"] == "gpt-4o,gpt-4o-mini"
        assert metadata["evaluation_total_tokens"] == 220
        assert "evaluation_cost_usd" not in metadata


# ---------------------------------------------------------------- LLMService.complete


def _response(text="answer", prompt=11, completion=7, logprobs=None):
    response = MagicMock()
    response.choices[0].message.content = text
    response.usage.prompt_tokens = prompt
    response.usage.completion_tokens = completion
    if logprobs is None:
        response.choices[0].logprobs = None
    else:
        content = []
        for token, logprob, top in logprobs:
            item = MagicMock()
            item.token, item.logprob = token, logprob
            item.top_logprobs = [MagicMock(token=t, logprob=lp) for t, lp in top]
            content.append(item)
        response.choices[0].logprobs.content = content
    return response


class TestComplete:
    def test_returns_text_usage_and_model(self):
        svc = LLMService(mode="live", api_key="k")
        with patch("mce.engine.llm._OpenAI") as client:
            client.return_value.chat.completions.create.return_value = _response()
            result = svc.complete("q", model="gpt-4o")
        assert (
            result.text,
            result.model,
            result.prompt_tokens,
            result.completion_tokens,
        ) == ("answer", "gpt-4o", 11, 7)
        assert result.logprobs is None

    def test_usage_is_added_to_the_current_scope(self):
        svc = LLMService(mode="live", api_key="k")
        with patch("mce.engine.llm._OpenAI") as client:
            client.return_value.chat.completions.create.return_value = _response()
            with track_usage() as usage:
                svc.get_completion("q", model="gpt-4o")
                svc.complete("q2", model="gpt-4o")
        assert (usage.prompt_tokens, usage.completion_tokens, usage.calls) == (
            22,
            14,
            2,
        )

    def test_logprobs_are_normalized(self):
        svc = LLMService(mode="live", api_key="k")
        response = _response(
            logprobs=[("Score", -0.1, []), ("4", -0.5, [("4", -0.5), ("5", -1.2)])]
        )
        with patch("mce.engine.llm._OpenAI") as client:
            client.return_value.chat.completions.create.return_value = response
            result = svc.complete("q", model="gpt-4o", logprobs=True, top_logprobs=5)
        assert result.logprobs == [
            {"token": "Score", "logprob": -0.1, "top": []},
            {
                "token": "4",
                "logprob": -0.5,
                "top": [
                    {"token": "4", "logprob": -0.5},
                    {"token": "5", "logprob": -1.2},
                ],
            },
        ]

    def test_extra_arguments_reach_the_api_but_sample_does_not(self):
        svc = LLMService(mode="live", api_key="k")
        with patch("mce.engine.llm._OpenAI") as client:
            create = client.return_value.chat.completions.create
            create.return_value = _response()
            svc.complete("q", model="gpt-4o", temperature=0.3, sample=2)
        kwargs = create.call_args.kwargs
        assert kwargs["temperature"] == 0.3
        assert "sample" not in kwargs

    def test_options_the_endpoint_rejects_are_dropped_and_remembered(self):
        svc = LLMService(mode="live", api_key="k")
        with patch("mce.engine.llm._OpenAI") as client:
            create = client.return_value.chat.completions.create
            create.side_effect = [
                Exception("logprobs is not supported"),
                _response(),
                _response(),
            ]
            first = svc.complete(
                "q", model="gpt-4o", temperature=0.0, logprobs=True, top_logprobs=5
            )
            second = svc.complete(
                "q2", model="gpt-4o", temperature=0.0, logprobs=True, top_logprobs=5
            )
        assert first.text == second.text == "answer"
        assert create.call_count == 3  # fail + retry, then straight through
        for call in create.call_args_list[1:]:
            assert not {"logprobs", "top_logprobs", "temperature"} & set(call.kwargs)

    def test_a_failure_without_optional_options_is_not_retried(self):
        svc = LLMService(mode="live", api_key="k")
        with patch("mce.engine.llm._OpenAI") as client:
            create = client.return_value.chat.completions.create
            create.side_effect = Exception("boom")
            with pytest.raises(RuntimeError, match="boom"):
                svc.complete("q", model="gpt-4o")
        assert create.call_count == 1

    def test_record_stores_usage_and_logprobs_and_replay_returns_them(self, tmp_path):
        cache = str(tmp_path / "c.json")
        recorder = LLMService(mode="record", cache_path=cache, api_key="k")
        response = _response(logprobs=[("4", -0.2, [("4", -0.2)])])
        with patch("mce.engine.llm._OpenAI") as client:
            client.return_value.chat.completions.create.return_value = response
            recorder.complete("q", model="gpt-4o", logprobs=True)

        replayer = LLMService(mode="replay", cache_path=cache)
        with track_usage() as usage:
            result = replayer.complete("q", model="gpt-4o")
        assert (result.text, result.prompt_tokens, result.completion_tokens) == (
            "answer",
            11,
            7,
        )
        assert result.logprobs == [
            {"token": "4", "logprob": -0.2, "top": [{"token": "4", "logprob": -0.2}]}
        ]
        assert (usage.prompt_tokens, usage.completion_tokens) == (11, 7)

    def test_replay_of_an_old_cache_entry_without_usage(self, tmp_path):
        svc = LLMService(mode="replay", cache_path=str(tmp_path / "c.json"))
        svc.cache[svc._hash_prompt("q", "gpt-4o")] = {"output": "old"}
        with track_usage() as usage:
            result = svc.complete("q", model="gpt-4o")
        assert (result.text, result.prompt_tokens, usage.calls) == ("old", 0, 1)

    def test_samples_of_the_same_prompt_have_their_own_cache_entries(self, tmp_path):
        cache = str(tmp_path / "c.json")
        recorder = LLMService(mode="record", cache_path=cache, api_key="k")
        with patch("mce.engine.llm._OpenAI") as client:
            client.return_value.chat.completions.create.side_effect = [
                _response("a"),
                _response("b"),
            ]
            recorder.complete("q", model="gpt-4o")
            recorder.complete("q", model="gpt-4o", sample=1)
        replayer = LLMService(mode="replay", cache_path=cache)
        assert replayer.complete("q", model="gpt-4o").text == "a"
        assert replayer.complete("q", model="gpt-4o", sample=1).text == "b"


# ---------------------------------------------------------------- metrics


class _FakeService(LLMService):
    """Replies with a fixed text and reports fixed usage per call."""

    def __init__(
        self, text="Reasoning: ok\nScore: 4", prompt=100, completion=20, model="gpt-4o"
    ):
        super().__init__(mode="live", api_key="k", model=model)
        self.text, self.prompt, self.completion = text, prompt, completion
        self.calls = 0

    def complete(self, prompt, model=None, system_prompt=None, *, sample=0, **kwargs):
        self.calls += 1
        record_usage(model or "gpt-4o", self.prompt, self.completion)
        return CompletionResult(
            text=self.text,
            model=model or "gpt-4o",
            prompt_tokens=self.prompt,
            completion_tokens=self.completion,
        )


_CONVERSATION = {"conversation_data": {"elements": "user: hi\nassistant: hello"}}


@pytest.fixture
def service(monkeypatch):
    svc = _FakeService()
    monkeypatch.setattr(LLMService, "get_instance", classmethod(lambda cls: svc))
    return svc


class TestMetricAccounting:
    def test_result_carries_the_evaluation_usage_and_cost(self, service):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        (result,) = Groundedness().compute_batch(["s1"], [_CONVERSATION])

        assert result.error is None
        assert result.value == pytest.approx(0.75)
        assert result.metadata["evaluation_model"] == "gpt-4o"
        assert result.metadata["evaluation_prompt_tokens"] == 100
        assert result.metadata["evaluation_completion_tokens"] == 20
        assert result.metadata["evaluation_total_tokens"] == 120
        assert result.metadata["evaluation_cost_usd"] == pytest.approx(
            100 * 2.5e-6 + 20 * 1e-5
        )

    def test_usage_is_summed_over_the_judge_samples(self, service, monkeypatch):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        monkeypatch.setenv("MCE_JUDGE_SAMPLES", "3")
        (result,) = Groundedness().compute_batch(["s1"], [_CONVERSATION])
        assert service.calls == 3
        assert result.metadata["evaluation_total_tokens"] == 360

    def test_each_resource_is_accounted_separately(self, service):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        first, second = Groundedness().compute_batch(
            ["s1", "s2"], [_CONVERSATION, _CONVERSATION]
        )
        assert (
            first.metadata["evaluation_total_tokens"]
            == second.metadata["evaluation_total_tokens"]
            == 120
        )

    def test_a_metric_that_makes_no_llm_call_has_no_evaluation_keys(self):
        from mce.providers.native.metrics.safety.tool_error import ToolError

        (result,) = ToolError().compute_batch(["t1"], [{"status": "OK"}])
        assert not any(key.startswith("evaluation_") for key in result.metadata)

    def test_usage_is_kept_when_the_judge_reply_is_unusable(self, service):
        from mce.providers.native.metrics.quality.groundedness import Groundedness

        service.text = "I cannot evaluate this."
        (result,) = Groundedness().compute_batch(["s1"], [_CONVERSATION])
        assert result.error and "Score" in result.error
        assert (
            result.metadata["evaluation_total_tokens"] == 120
        )  # the call was paid for

    def test_tool_calls_scored_in_worker_threads_are_all_counted(self, service):
        from mce.providers.native.metrics.quality.tool_utilization_accuracy import (
            ToolUtilizationAccuracy,
        )

        spans = [
            {
                "executionId": f"tc{i}",
                "toolName": "search",
                "toolArguments": '{"q": "x"}',
                "outputContent": "result",
            }
            for i in range(5)
        ]
        (result,) = ToolUtilizationAccuracy().compute_batch(
            ["s1"], [{"tool_spans": spans}]
        )

        assert result.error is None
        assert service.calls == 5
        assert result.metadata["evaluation_total_tokens"] == 5 * 120
        assert result.metadata["evaluation_prompt_tokens"] == 500


class TestFailuresAreNotScores:
    @pytest.mark.parametrize(
        ("module", "name", "context"),
        [
            ("quality.groundedness", "Groundedness", {}),
            ("quality.goal_success_rate", "GoalSuccessRate", {}),
            ("quality.task_delegation_accuracy", "TaskDelegationAccuracy", {}),
            ("quality.tool_utilization_accuracy", "ToolUtilizationAccuracy", {}),
        ],
    )
    def test_missing_input_is_an_error_result(self, service, module, name, context):
        import importlib

        cls = getattr(
            importlib.import_module(f"mce.providers.native.metrics.{module}"), name
        )
        (result,) = cls().compute_batch(["x"], [context])
        assert isinstance(result, MetricResult)
        assert result.error
        assert service.calls == 0
