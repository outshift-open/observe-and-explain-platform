#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Summarize the TrajectoryContext of one trajectory file. Makes no model calls."""

import argparse
import sys
from collections import Counter
from pathlib import Path

from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext
from stateful_evals_be.integrations.files import load_trajectory_file

HERE = Path(__file__).resolve().parent
DEFAULT_FILE = HERE / "data" / "trajectory_e7f32992.json"

# TemporalMetricsProcessor.evaluate_spans has no judge-free entry point, so this
# mirrors its construction and per-span dedup exactly, skipping only judging,
# scoring, and sampling (none of which change what TrajectoryContext records).
_P = TemporalMetricsProcessor


def build_context(path: Path) -> tuple[str, int, list[dict], TrajectoryContext]:
    """Follow TemporalMetricsProcessor.evaluate_spans, minus judging and scoring."""
    session_id, loaded = load_trajectory_file(path)
    raw_spans = sorted(loaded, key=lambda s: str(s.get("Timestamp", "")))
    raw_spans = _P._deduplicate_spans(raw_spans)
    spans_by_id = {str(s["SpanId"]): s for s in raw_spans if s.get("SpanId")}

    context = TrajectoryContext(
        policy_text=_P._extract_system_message(raw_spans),
        tool_definitions=_P._extract_tool_definitions(raw_spans),
        coordination_context=_P._extract_coordination_context(raw_spans),
    )
    _P._ingest_agent_semantic_contracts(context, raw_spans)

    span_dicts = []
    skip_next_llm = False  # an agent span that already shows routing or the
    # final answer means the LLM span right after it just repeats that content
    for index, raw_span in enumerate(raw_spans):
        span_dict = _P._otel_trace_to_span_dict(raw_span, spans_by_id=spans_by_id)
        span_dicts.append(span_dict)
        entity_type = span_dict["entity_type"]
        if entity_type == "agent":
            skip_next_llm = _P._agent_span_has_routing_or_answer(raw_span)
        elif entity_type == "tool":
            skip_next_llm = False
        elif entity_type == "llm" and skip_next_llm:
            skip_next_llm = False
        context.ingest_span(span_dict, span_index=index)

    _P._synchronize_final_answer(object.__new__(_P), context, raw_spans)
    return session_id, len(loaded), span_dicts, context


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", type=Path, default=DEFAULT_FILE, help="file or folder"
    )
    path = parser.parse_args().path.expanduser()
    if path.is_dir():  # a folder of trajectories: inspect the smallest one
        found = sorted(
            path.glob("trajectory_*.json"), key=lambda p: (p.stat().st_size, p.name)
        )
        path = found[0] if found else path / "trajectory_*.json"
    if not path.is_file():
        sys.exit(f"Trajectory file not found: {path}. See quickstart/README.md.")

    try:
        session_id, loaded, span_dicts, context = build_context(path)
    except ValueError as exc:
        sys.exit(f"{path}: {exc}")
    types = Counter(s["entity_type"] for s in span_dicts)
    facts = Counter(f.fact_type for f in context.evidence)
    claims = Counter(c.claim_type for c in context.claims)
    events = Counter(e.event_type for e in context.coordination_events)
    print(f"file:     {path.name}")
    print(f"session:  {session_id}")
    print(f"spans:    {loaded} read, {len(span_dicts)} after de-duplication")
    print(f"types:    {', '.join(f'{k}={v}' for k, v in types.most_common())}")
    print(f"evidence: {', '.join(f'{k}={v}' for k, v in facts.most_common()) or '-'}")
    print(f"claims:   {', '.join(f'{k}={v}' for k, v in claims.most_common()) or '-'}")
    print(
        f"coordination events: {', '.join(f'{k}={v}' for k, v in events.most_common()) or '-'}"
    )
    print("intents:")
    for index, intent in enumerate(context.intents):
        print(f"  intent:{index}  {intent.status:<11}  {intent.name}")
    answer = context.get_final_answer_context()["final_answer"].strip()
    first_line = answer.splitlines()[0] if answer else "-"
    print(f"final answer: {first_line[:120]}")


if __name__ == "__main__":
    main()
