#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for adaptive span sampling (tail-weighted bucket strategy).

All tests are fully local — no network, no LLM calls, no K8s.
The MCE/LLM layer is mocked so we only validate the sampling logic.
"""

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock


from metrics_computation_engine.models.requests import LLMJudgeConfig
from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.models.requests import SamplingConfig, TemporalMetricOptions


# ─── Fixture helpers ────────────────────────────────────────────────────────


def _make_span(
    span_id: str,
    span_type: str,  # "llm" | "tool" | "other"
    name: str,
    output: str = "ok",
    contains_error: bool = False,
) -> Dict[str, Any]:
    """Build a minimal OTel-style raw span dict that the processor can parse."""
    attrs: Dict[str, Any] = {
        "gen_ai.system": "openai" if span_type == "llm" else "",
        "gen_ai.request.model": name if span_type == "llm" else "",
        "output.value": output,
    }
    if contains_error:
        attrs["error"] = "true"

    span: Dict[str, Any] = {
        "SpanId": span_id,
        "TraceId": "trace-001",
        "ParentSpanId": "",
        "Timestamp": f"2024-01-01T00:00:{span_id.zfill(6)}Z",
        "ServiceName": "test-app",
        "SpanName": name,
        "SpanAttributes": attrs,
        "ResourceAttributes": {},
        "Events": [],
        "Links": [],
        "StatusCode": "ERROR" if contains_error else "OK",
        "StatusMessage": "",
        "Duration": 100,
    }

    # Inject span-type hints the processor relies on
    if span_type == "llm":
        span["SpanAttributes"]["gen_ai.usage.prompt_tokens"] = "10"
        span["SpanAttributes"]["gen_ai.usage.completion_tokens"] = "5"
        span["SpanAttributes"]["gen_ai.prompt.0.content"] = "user: hello"
        span["SpanAttributes"]["gen_ai.completion.0.content"] = output
    elif span_type == "tool":
        span["SpanAttributes"]["tool.name"] = name
        span["SpanAttributes"]["input.value"] = "{}"
        span["SpanAttributes"]["output.value"] = output
    # "other" spans get no special attributes

    return span


def _make_processor(
    sampling: Optional[SamplingConfig] = None,
) -> TemporalMetricsProcessor:
    llm_config = LLMJudgeConfig(
        LLM_API_KEY="sk-test",
        LLM_MODEL_NAME="gpt-4o",
        LLM_BASE_MODEL_URL="https://api.openai.com/v1",
    )
    options = TemporalMetricOptions(
        use_fatal_mode=False,
        sampling=sampling,
    )
    return TemporalMetricsProcessor(
        llm_config=llm_config,
        options=options,
    )


def _good_mce_response(metric_name: str) -> Dict[str, Any]:
    """MCE stub returning a passing score."""
    short = metric_name.split(".")[-1]
    return {
        "results": [
            {
                "metric_name": short,
                "value": 1.0,
                "reasoning": "stub pass",
                "success": True,
            }
        ],
        "failed_metrics": [],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }


# ─── Unit tests: _build_sampling_plan ───────────────────────────────────────


def _make_minimal_spans(pattern: List[str]) -> List[Dict]:
    """
    Build a raw span list from a pattern like ['other','llm','tool','llm','other'].
    Span IDs are just str(index).
    """
    spans = []
    for i, t in enumerate(pattern):
        name = (
            "azure/gpt-4o"
            if t == "llm"
            else (f"tool_{i}" if t == "tool" else f"node_{i}")
        )
        spans.append(_make_span(str(i), t, name))
    return spans


class TestBuildSamplingPlan:
    def setup_method(self):
        self.cfg = SamplingConfig(strategy="tail_weighted")
        self.proc = _make_processor(self.cfg)

    def _plan(self, pattern: List[str]):
        spans = _make_minimal_spans(pattern)
        spans_by_id = {str(s["SpanId"]): s for s in spans}
        return self.proc._build_sampling_plan(spans, spans_by_id, self.cfg)

    def test_first_and_last_are_anchors(self):
        anchors, pos_map = self._plan(["other", "llm", "other", "tool", "llm", "other"])
        evaluable = sorted(pos_map.keys())
        assert evaluable[0] in anchors, "First evaluable span must be an anchor"
        assert evaluable[-1] in anchors, "Last evaluable span must be an anchor"

    def test_only_evaluable_spans_in_pos_map(self):
        pattern = ["other", "llm", "other", "tool", "other"]
        _, pos_map = self._plan(pattern)
        # indices 1 (llm) and 3 (tool) are evaluable; 0, 2, 4 are other
        assert set(pos_map.keys()) == {1, 3}

    def test_error_span_and_neighbors_are_anchors(self):
        # pattern: other llm llm(error) llm other
        spans = _make_minimal_spans(["other", "llm", "llm", "llm", "other"])
        # mark index 2 as error
        spans[2]["StatusCode"] = "ERROR"
        spans[2]["SpanAttributes"]["error"] = "true"
        spans_by_id = {str(s["SpanId"]): s for s in spans}
        anchors, _ = self.proc._build_sampling_plan(spans, spans_by_id, self.cfg)
        # evaluable: 1, 2, 3 → error at 2, neighbors 1 and 3 should be anchors
        assert 2 in anchors, "Error span itself must be anchor"
        assert 1 in anchors, "Span before error must be anchor"
        assert 3 in anchors, "Span after error must be anchor"

    def test_post_large_tool_llm_is_anchor(self):
        big_output = "x" * 3000  # exceeds default 2000 char threshold
        spans = [
            _make_span("0", "other", "orchestrator"),
            _make_span("1", "tool", "read_document", output=big_output),
            _make_span("2", "llm", "azure/gpt-4o"),
            _make_span("3", "llm", "azure/gpt-4o"),
        ]
        spans_by_id = {str(s["SpanId"]): s for s in spans}
        anchors, _ = self.proc._build_sampling_plan(spans, spans_by_id, self.cfg)
        assert 2 in anchors, "LLM after large tool output must be anchor"
        # span 3 is NOT a post-large-tool candidate (tool before it was not large)
        assert 3 not in anchors or 3 == sorted(anchors)[-1], (
            "Span 3 should only be anchor if it's the last evaluable span"
        )

    def test_single_evaluable_span_is_both_anchors(self):
        anchors, pos_map = self._plan(["other", "llm", "other"])
        assert len(pos_map) == 1
        assert list(pos_map.keys())[0] in anchors


# ─── Unit tests: _should_evaluate_span ──────────────────────────────────────


class TestShouldEvaluateSpan:
    def setup_method(self):
        self.cfg = SamplingConfig(
            strategy="tail_weighted",
            early_rate=0.0,  # skip ALL early spans (deterministic)
            mid_rate=0.0,  # skip ALL mid spans
        )
        self.proc = _make_processor(self.cfg)

    def _make_pos_map(self, count: int) -> Dict[int, int]:
        return {i: i for i in range(count)}

    def test_strategy_none_always_evaluates(self):
        cfg_none = SamplingConfig(strategy="none")
        pos_map = self._make_pos_map(10)
        for idx in range(10):
            assert self.proc._should_evaluate_span(idx, pos_map, set(), cfg_none)

    def test_anchors_always_evaluated_regardless_of_rate(self):
        pos_map = self._make_pos_map(10)
        anchors = {0, 5, 9}
        for anchor_idx in anchors:
            assert self.proc._should_evaluate_span(
                anchor_idx, pos_map, anchors, self.cfg
            ), f"Anchor span {anchor_idx} must always be evaluated"

    def test_late_zone_always_evaluated(self):
        # 10 evaluable spans; late = positions 7,8,9 (≥70%)
        pos_map = self._make_pos_map(10)
        anchors: set = set()
        for idx in [7, 8, 9]:
            assert self.proc._should_evaluate_span(idx, pos_map, anchors, self.cfg), (
                f"Late-zone span {idx} must always be evaluated"
            )

    def test_early_zone_skipped_at_zero_rate(self):
        # 10 spans; early = positions 0-3 (norm_pos < 0.40)
        # With early_rate=0.0, non-anchor early spans should be skipped
        pos_map = self._make_pos_map(10)
        anchors: set = set()
        skipped = [
            idx
            for idx in [1, 2, 3]  # skip index 0 — it's typically an anchor
            if not self.proc._should_evaluate_span(idx, pos_map, anchors, self.cfg)
        ]
        assert len(skipped) == 3, (
            f"All non-anchor early spans should be skipped, got {skipped}"
        )

    def test_deterministic_same_index_same_result(self):
        cfg = SamplingConfig(strategy="tail_weighted", early_rate=0.5, mid_rate=0.5)
        pos_map = self._make_pos_map(20)
        anchors: set = set()
        results_run1 = [
            self.proc._should_evaluate_span(i, pos_map, anchors, cfg) for i in range(20)
        ]
        results_run2 = [
            self.proc._should_evaluate_span(i, pos_map, anchors, cfg) for i in range(20)
        ]
        assert results_run1 == results_run2, (
            "Sampling must be deterministic for same inputs"
        )


# ─── Integration test: sampling reduces MCE calls ───────────────────────────


class TestSamplingReducesMceCalls:
    """
    End-to-end test of evaluate_session with a mocked MCE and span fetcher.
    Verifies that tail_weighted sampling calls MCE fewer times than baseline.
    """

    # Mirror of our real session: 4 early llm/tool + 2 mid tool + 3 late llm
    SESSION_PATTERN = [
        ("other", "noa-trip-planner"),
        ("other", "LangGraph"),
        ("other", "moderator"),
        ("llm", "azure/gpt-4o"),  # eval #1 — anchor (first)
        ("other", "RunnableCallable"),
        ("other", "schedule_agent"),
        ("llm", "azure/gpt-4o"),  # eval #2 — early
        ("other", "should_continue"),
        ("other", "schedule_tools"),
        ("tool", "list_documents"),  # eval #3 — early
        ("other", "schedule_agent"),
        ("llm", "azure/gpt-4o"),  # eval #4 — early
        ("other", "schedule_tools"),
        ("tool", "read_document"),  # eval #5 — mid
        ("tool", "read_document"),  # eval #6 — mid
        ("tool", "read_document"),  # eval #7 — late
        ("other", "schedule_agent"),
        ("llm", "azure/gpt-4o"),  # eval #8 — late
        ("other", "should_continue"),
        ("other", "moderator"),
        ("llm", "azure/gpt-4o"),  # eval #9 — anchor (last)
        ("other", "RunnableCallable"),
        ("other", "finalize"),
    ]

    def _build_raw_spans(self) -> List[Dict]:
        spans = []
        for i, (t, name) in enumerate(self.SESSION_PATTERN):
            output = (
                ("document content " * 10) + str(i)
                if t == "tool"
                else f"response text {i}"
            )
            spans.append(_make_span(str(i), t, name, output=output))
        return spans

    def _run_eval(self, sampling: Optional[SamplingConfig]) -> Dict[str, Any]:
        proc = _make_processor(sampling)
        raw_spans = self._build_raw_spans()

        mce_call_count = 0

        def mock_mce(span_dict, *, context_state, policy, metrics):
            nonlocal mce_call_count
            mce_call_count += 1
            responses = [_good_mce_response(metric)["results"][0] for metric in metrics]
            return {
                "results": responses,
                "failed_metrics": [],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            }

        proc.fetch_spans_for_session = MagicMock(return_value=raw_spans)
        proc.compute_span_state_delta = mock_mce

        result = proc.evaluate_session("test-session-123")
        return {
            "result": result,
            "mce_calls": mce_call_count,
        }

    def test_baseline_evaluates_all_spans(self):
        out = self._run_eval(None)  # no sampling
        # 9 evaluable spans, one combined primitive call per span.
        assert out["mce_calls"] == 9, (
            f"Baseline should make 9 combined calls, got {out['mce_calls']}"
        )
        assert out["result"].spans_sampled_out == 0

    def test_tail_weighted_reduces_mce_calls(self):
        cfg = SamplingConfig(strategy="tail_weighted", early_rate=0.0, mid_rate=0.0)
        out = self._run_eval(cfg)
        assert out["mce_calls"] < 9, (
            f"Sampled run must use fewer than 9 combined calls, got {out['mce_calls']}"
        )
        assert out["result"].spans_sampled_out > 0, (
            "At least some spans should be sampled out"
        )

    def test_trajectory_score_preserved(self):
        """Sampling must not change trajectory_score when all scores are perfect."""
        cfg = SamplingConfig(strategy="tail_weighted", early_rate=0.25, mid_rate=0.60)
        baseline = self._run_eval(None)
        sampled = self._run_eval(cfg)
        # Both should pass (trajectory_score=1) since mock always returns score=1.0
        assert (
            baseline["result"].trajectory_score == sampled["result"].trajectory_score
        ), (
            "trajectory_score must be consistent between baseline and sampled runs "
            "when all evaluated spans pass"
        )

    def test_sampled_out_count_matches_gap(self):
        cfg = SamplingConfig(strategy="tail_weighted", early_rate=0.0, mid_rate=0.0)
        out = self._run_eval(cfg)
        result = out["result"]
        total_evaluable = result.mce_spans_evaluated + result.spans_sampled_out
        assert total_evaluable == 9, (
            f"mce_spans_evaluated + spans_sampled_out must equal 9 evaluable spans, "
            f"got {result.mce_spans_evaluated} + {result.spans_sampled_out}"
        )
