#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Functional, end-to-end test of the pipeline (load -> normalize -> verify
-> dump) against a real reference trace shipped as a fixture, so this test
needs no machine-specific path and runs in CI.

The fixture (``noa_trip_planner.otel_export.jsonl``) mixes two live
instrumentation layers on the same trace: real ioa_observe SDK spans
(``{entity}.agent``/``.chat``/``.tool``/``.graph`` names, dispatched by
``norm.ioa_observe.build_kg``) and spans from
``opentelemetry-instrumentation-langchain``, which observe-sdk activates by
default whenever langchain/langgraph is installed -- OTel GenAI-semconv names
like ``execute_task <name>``/``invoke_agent LangGraph`` that don't match any
dispatched span-name suffix and are silently ignored by design: the current
architecture only ever builds nodes from a span whose name it recognizes, it
never tries to account for every row in the trace.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from norm import dump_jsonld, infer_run_id, load_otel_export, normalize, verify_kg
from norm.ioa_observe.fields import attrs

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "noa_trip_planner.otel_export.jsonl"


@pytest.fixture(scope="module")
def loaded_spans():
    return load_otel_export(FIXTURE)


def test_load_otel_export_reads_every_row(loaded_spans) -> None:
    assert len(loaded_spans) == 98


def test_full_pipeline_load_normalize_verify_dump(loaded_spans, tmp_path) -> None:
    run_id = infer_run_id(loaded_spans)
    assert run_id == "9a419e60-fa38-40de-a1c1-65e687a6e5a3"

    nodes, edges = normalize(loaded_spans)
    assert len(nodes) > 100, "expected a substantial graph from a 98-span real trace"
    assert edges

    kg_report = verify_kg(nodes, edges, run_id)
    for name, result in kg_report["structural_checks"].items():
        if result.get("reason"):
            continue
        assert result["ok"], f"{name} failed: {result['violations'][:5]}"

    doc = dump_jsonld(nodes, edges, tmp_path / "kg.jsonld")
    assert doc["@graph"]
    written = (tmp_path / "kg.jsonld").read_text(encoding="utf-8")
    assert '"@graph"' in written


def test_every_agent_span_produces_one_agent_call(loaded_spans) -> None:
    """Regression guard: build_kg's ``*.agent`` dispatch must fire exactly
    once per matching span -- no dropped or duplicated AgentCalls."""
    agent_span_count = sum(
        1 for s in loaded_spans if str(s.get("SpanName") or "").endswith(".agent")
    )

    nodes, _edges = normalize(loaded_spans)
    agent_call_count = sum(1 for n in nodes if n.get("node_type") == "AgentCall")

    assert agent_span_count > 0
    assert agent_call_count == agent_span_count


def test_every_chat_span_with_model_info_produces_one_llm_call(loaded_spans) -> None:
    """Regression guard: no phantom/placeholder LLMCall nodes -- a ``.chat``
    span only ever produces one when it actually carries provider/model
    attributes (handle_chat returns early otherwise), and every span that
    does carry them produces exactly one."""
    real_chat_spans = [
        s
        for s in loaded_spans
        if str(s.get("SpanName") or "").endswith(".chat")
        and (attrs(s).get("gen_ai.provider.name") or attrs(s).get("gen_ai.request.model"))
    ]

    nodes, _edges = normalize(loaded_spans)
    llm_call_count = sum(1 for n in nodes if n.get("node_type") == "LLMCall")

    assert real_chat_spans
    assert llm_call_count == len(real_chat_spans)


def test_node_type_distribution_is_stable(loaded_spans) -> None:
    """Pins the current, real output shape of this fixture -- any change here
    should be a deliberate architecture change, not a silent regression."""
    nodes, _edges = normalize(loaded_spans)
    counts = Counter(n["node_type"] for n in nodes)

    assert counts["Session"] == 1
    assert counts["MASCall"] == 1
    assert counts["MAS"] == 1
    assert counts["AgentCall"] == 16
    assert counts["LLMCall"] == 12
    assert counts["LLM"] == 1
