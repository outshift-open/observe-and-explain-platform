#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Evaluating a normalized trajectory (no OTel involved)."""

import json
from unittest.mock import Mock

import pytest
from metrics_computation_engine.models.requests import LLMJudgeConfig
from stateful_evals_be.evaluation import trajectory_input as ti
from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.models.requests import TemporalMetricOptions

SYSTEM = "You are a travel specialist. Use your tools."
USER = "Is there a direct train from A to B?"

TOOL_CALL = {"type": "tool_call", "id": "call_1", "name": "read_document", "arguments": {}}


def system_parts(text):
    return json.dumps([{"type": "text", "content": text}])


def messages(*items):
    return json.dumps(list(items))


USER_MESSAGE = {"role": "user", "parts": [{"type": "text", "content": USER}]}
# system instructions and chat messages sit back to back in an LLM input State
LLM_IN_1 = system_parts(SYSTEM + "\nBe brief.") + "\n\n" + messages(USER_MESSAGE)
LLM_OUT_1 = messages({"role": "assistant", "parts": [TOOL_CALL], "finish_reason": "tool_calls"})
LLM_IN_2 = (
    system_parts(SYSTEM)
    + "\n\n"
    + messages(
        USER_MESSAGE,
        {"role": "assistant", "parts": [TOOL_CALL]},
        {"role": "tool", "parts": [{"type": "tool_call_response", "id": "call_1", "response": "Table: A->B direct, 2h"}]},
    )
)
LLM_OUT_2 = messages(
    {
        "role": "assistant",
        "parts": [{"type": "text", "content": "Yes, there is a direct train from A to B (2h)."}],
        "finish_reason": "stop",
    }
)


def step(tid, kind, name, start, i, o, *, agent="specialist", desc="", ok=True, parent="agentcall:a1"):
    return {
        "transition_id": tid,
        "call_id": tid.replace("transition", kind + "call"),
        "kind": kind,
        "name": name,
        "description": desc,
        "agent_id": agent,
        "parent_id": "" if kind == "agent" else parent,
        "success": ok,
        "start_time": start,
        "duration_ms": 1000.0,
        "input_text": i,
        "output_text": o,
    }


@pytest.fixture
def trajectory():
    return {
        "session_id": "s1",
        "steps": [
            step("transition:a1", "agent", "specialist", 1.0, json.dumps({"args": [{"messages": []}]}), ""),
            step("transition:t2", "llm", "gpt-4o", 2.0, LLM_IN_1, LLM_OUT_1),
            step(
                "transition:t3", "tool", "read_document", 3.0,
                '{"args": [], "kwargs": {}}', '"Table: A->B direct, 2h"', desc="Reads a document",
            ),
            step("transition:t4", "llm", "gpt-4o", 5.0, LLM_IN_2, LLM_OUT_2),
        ],
    }


# ---------------------------------------------------------------- parsing

def test_parse_llm_input_splits_system_and_messages_and_tolerates_raw_newlines():
    system, parsed = ti.parse_llm_input(LLM_IN_1)
    assert system == SYSTEM + "\nBe brief."
    assert parsed == [{"role": "user", "content": USER}]


def test_parse_llm_input_keeps_tool_history():
    _, parsed = ti.parse_llm_input(LLM_IN_2)
    assert {m["role"] for m in parsed} == {"user", "assistant", "tool"}
    tool = next(m for m in parsed if m["role"] == "tool")
    assert tool["tool_call_id"] == "call_1"
    assistant = next(m for m in parsed if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["id"] == "call_1"


def test_parse_llm_input_falls_back_to_plain_text():
    system, parsed = ti.parse_llm_input("just some prompt text")
    assert system == ""
    assert parsed == [{"role": "user", "content": "just some prompt text"}]


def test_parse_llm_output_and_payloads():
    assert ti.parse_llm_output(LLM_OUT_2)[0]["content"].startswith("Yes, there is")
    assert ti.parse_llm_output("plain answer") == [{"role": "assistant", "content": "plain answer"}]
    assert ti.parse_payload('{"args": [], "kwargs": {"k": 1}}') == {"args": [], "kwargs": {"k": 1}}
    assert ti.parse_payload('"a string"') == "a string"
    assert ti.parse_payload("not json") == {"value": "not json"}
    assert ti.parse_payload("") is None


def test_span_dicts_use_step_ids_and_match_tool_call_ids(trajectory):
    spans = ti.build_span_dicts(trajectory)
    assert [s["entity_type"] for s in spans] == ["agent", "llm", "tool", "llm"]
    assert spans[1]["span_id"] == "llmcall:t2"
    assert spans[1]["agent_id"] == "specialist"
    assert spans[1]["parent_span_id"] == "agentcall:a1" and spans[0]["parent_span_id"] is None
    assert spans[2]["attributes"] == {"gen_ai.tool.call.id": "call_1"}
    assert spans[2]["tool_definition"] == {"name": "read_document", "description": "Reads a document"}
    assert spans[1]["input_payload"]["messages"][0] == {"role": "system", "content": SYSTEM + "\nBe brief."}
    assert all(s["raw_span_data"] is None and s["trace_id"] is None for s in spans)
    assert spans[2]["duration_ns"] == 1_000_000_000


def test_session_inputs_come_from_the_trajectory(trajectory):
    spans = ti.build_span_dicts(trajectory)
    assert ti.find_root_request(spans) == USER
    assert ti.root_policy(spans) == SYSTEM + "\nBe brief."
    assert ti.declared_roster(spans) == [("specialist", 0)]
    assert ti.find_final_answer(spans) == ("Yes, there is a direct train from A to B (2h).", 3)
    assert {c[0] for c in ti.semantic_contracts(spans)} == {"specialist"}


def test_final_answer_skips_routing_decisions():
    spans = [
        {"entity_type": "llm", "output_payload": {"messages": [{"role": "assistant", "content": "The answer is 42."}]}},
        {"entity_type": "llm", "output_payload": {"messages": [{"role": "assistant", "content": '{"next":"FINISH"}'}]}},
    ]
    assert ti.find_final_answer(spans) == ("The answer is 42.", 0)


# ---------------------------------------------------------------- evaluation


@pytest.fixture
def processor(monkeypatch):
    monkeypatch.setattr(TemporalMetricsProcessor, "_warm_inprocess_metric_catalog", lambda self: None)
    monkeypatch.setattr("stateful_evals_be.evaluation.processor.LLMClient", Mock())
    proc = TemporalMetricsProcessor(
        llm_config=LLMJudgeConfig(LLM_MODEL_NAME="m", LLM_BASE_MODEL_URL="http://x", LLM_API_KEY="k"),
        options=TemporalMetricOptions(use_fatal_mode=False),
    )
    proc.compute_span_state_delta = Mock(
        side_effect=lambda span, **kw: {
            "results": [
                {"metric_name": m, "value": 1.0, "reasoning": "pass", "success": True}
                for m in kw["metrics"]
            ],
            "failed_metrics": [],
            "usage": {},
        }
    )
    proc._run_unified_final_audit = Mock(side_effect=lambda **_: ([], [], [], [], {}))
    return proc


def test_evaluate_trajectory_scores_every_judged_step(processor, trajectory):
    result = processor.evaluate_trajectory(trajectory)

    assert result.error is None
    assert result.total_spans == 4
    by_transition = {}
    for smr in result.span_metric_results:
        by_transition.setdefault(smr.transition_id, set()).add(smr.metric_name)
    # agent steps are not judged; llm steps get all three, tool steps no Groundedness
    assert set(by_transition) == {"transition:t2", "transition:t3", "transition:t4"}
    assert len(by_transition["transition:t3"]) == 2
    assert len(by_transition["transition:t2"]) == 3
    assert all(m.span_id.startswith(("llmcall:", "toolcall:")) for m in result.span_metric_results)
    assert all(m.trace_id == "" for m in result.span_metric_results)


def test_evaluate_trajectory_records_context_per_transition(processor, trajectory):
    result = processor.evaluate_trajectory(trajectory)

    contexts = result.transition_contexts
    assert contexts, "steps should contribute context"
    assert set(contexts) <= {"transition:a1", "transition:t2", "transition:t3", "transition:t4"}
    tool_ctx = contexts["transition:t3"]
    assert tool_ctx["evidence"][0]["fact_type"] == "tool_output"
    assert tool_ctx["evidence"][0]["tool_call_id"] == "call_1"
    assert tool_ctx["evidence"][0]["span_id"] == "toolcall:t3"
    json.dumps(contexts)  # must be JSON-serializable for the KG


def test_evaluate_trajectory_sets_the_final_answer(processor, trajectory):
    result = processor.evaluate_trajectory(trajectory)
    answers = [d["final_answer"]["text"] for d in result.transition_contexts.values() if "final_answer" in d]
    assert any(a.startswith("Yes, there is a direct train") for a in answers)


def test_evaluate_trajectory_reports_missing_steps(processor):
    result = processor.evaluate_trajectory({"session_id": "s1", "steps": []})
    assert result.error and "No trajectory steps" in result.error


def test_evaluate_trajectory_reports_malformed_steps(processor):
    result = processor.evaluate_trajectory({"session_id": "s1", "steps": [{"kind": "llm"}]})
    assert result.error


def test_first_transition_carries_the_context_that_exists_before_the_first_step(processor, trajectory):
    result = processor.evaluate_trajectory(trajectory)
    first = result.transition_contexts["transition:a1"]
    # the root policy and the user request are recorded as evidence up front
    assert "policy_rule" in {e["fact_type"] for e in first["evidence"]}


def test_transition_contexts_are_flat(processor, trajectory):
    result = processor.evaluate_trajectory(trajectory)
    known = {"evidence", "claims", "intents", "work_units", "provenance_links", "coordination_events", "flags", "final_answer"}
    for delta in result.transition_contexts.values():
        assert set(delta) <= known


def test_context_deltas_replay_to_gapless_indexes(processor, trajectory):
    """Per-step deltas together cover every context item exactly once."""
    result = processor.evaluate_trajectory(trajectory)

    evidence = {}
    for tid in ("transition:a1", "transition:t2", "transition:t3", "transition:t4"):
        for item in result.transition_contexts.get(tid, {}).get("evidence", []):
            evidence[item["index"]] = item
    assert evidence
    assert sorted(evidence) == list(range(len(evidence)))


def test_merge_context_delta():
    from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext

    base = {"evidence": [{"index": 0}], "intents": [{"index": 0, "status": "a"}]}
    TrajectoryContext.merge_context_delta(
        base,
        {
            "evidence": [{"index": 1}],
            "intents": [{"index": 0, "status": "b"}, {"index": 1, "status": "a"}],
            "claims": [{"index": 0}],
            "final_answer": {"span_index": 3, "text": "done"},
        },
    )
    assert base == {
        "evidence": [{"index": 0}, {"index": 1}],
        "intents": [{"index": 0, "status": "b"}, {"index": 1, "status": "a"}],
        "claims": [{"index": 0}],
        "final_answer": {"span_index": 3, "text": "done"},
    }
