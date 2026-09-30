#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""End-to-end quickstart: load → normalize → verify on the bundled reference trace.

Mirrors norm-eval/validate_trace.py with pytest assertions instead of
report files. This is the canonical smoke test for the public API.
"""

from __future__ import annotations

from pathlib import Path

from norm import dump_jsonld, infer_run_id, load_otel_export, normalize, verify_kg

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "otel_traces_export.jsonl"


def test_validate_trace_load_normalize_verify(tmp_path: Path) -> None:
    spans = load_otel_export(FIXTURE)
    run_id = infer_run_id(spans)

    assert len(spans) == 89
    assert run_id == "a21ec8f6-c862-411b-a6cf-eb681aabcf51"

    nodes, edges = normalize(spans)
    assert len(nodes) > 100
    assert edges

    report = verify_kg(nodes, edges, run_id)
    for name, result in report["structural_checks"].items():
        if result.get("reason"):
            continue
        assert result["ok"], f"{name}: {result['violations'][:3]}"

    doc = dump_jsonld(nodes, edges, tmp_path / "kg.jsonld")
    assert doc["@graph"]
