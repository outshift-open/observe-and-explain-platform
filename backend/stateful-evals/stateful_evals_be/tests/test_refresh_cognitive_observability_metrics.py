#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import csv
import json

from stateful_evals_be.scripts.refresh_cognitive_observability_metrics import (
    METRIC_NAMES,
    _combine_delegation_accuracy,
    _merge_metrics,
    summarize,
)


def test_merge_preserves_current_communication_efficiency_name() -> None:
    original = [
        {
            "high_level_metric": name,
            "score": 1,
            "reasoning": name,
        }
        for name in METRIC_NAMES
    ]

    merged = _merge_metrics(original, [])

    communication = next(
        metric
        for metric in merged
        if metric["high_level_metric"] == "Communication Efficiency"
    )
    assert communication["reasoning"] == "Communication Efficiency"


def test_delegation_accuracy_combines_routing_and_ownership_subscores() -> None:
    routing = {
        "high_level_metric": "Delegation Accuracy",
        "score": 1,
        "reasoning": "Executed routing was accurate.",
        "metadata": {"definition_version": "paper_v1"},
    }
    ownership = {
        "high_level_metric": "Delegation Accuracy",
        "score": 0,
        "reasoning": "A required subtask had no owner.",
        "fatal_failures": [{"classification": "FATAL"}],
        "metadata": {"definition_version": "paper_v2"},
    }

    combined = _combine_delegation_accuracy(routing, ownership)

    assert combined["score"] == 0
    assert combined["metadata"]["subscores"] == {
        "executed_routing_accuracy": 1,
        "ownership_completeness": 0,
    }
    assert combined["metadata"]["executed_routing_result_reused"] is True


def test_challenge_summary_ignores_checker_labels(tmp_path) -> None:
    scores = (0, 1, 0)
    checker_values = (True, False, None)
    for index, (score, checker_present) in enumerate(zip(scores, checker_values)):
        run_dir = tmp_path / "runs" / "dataset" / f"run-{index}"
        run_dir.mkdir(parents=True)
        (run_dir / "evaluation_record.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "hash": f"run-{index}",
                    "domain": "sre-triage",
                    "dataset": "dataset",
                    "scenario": "CE-1-missing-evidence",
                    "playbook_code": "CE-1",
                    "checker_present": checker_present,
                    "model": "test-model",
                    "metrics": [
                        {
                            "high_level_metric": "Verification Quality",
                            "score": score,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    summarize(output_dir=tmp_path)

    with (tmp_path / "challenge_observability.csv").open(
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))
    ce1 = next(row for row in rows if row["challenge"] == "CE-1")

    assert ce1["n"] == "3"
    assert ce1["target_evaluated"] == "3"
    assert ce1["target_failures"] == "2"
    assert "checker_positive" not in ce1


def test_summary_keeps_same_hash_from_different_datasets_separate(
    tmp_path,
) -> None:
    for dataset, score in (("sre-v1", 0), ("sre-v1-part2", 1)):
        run_dir = tmp_path / "runs" / dataset / "shared-hash"
        run_dir.mkdir(parents=True)
        (run_dir / "evaluation_record.json").write_text(
            json.dumps(
                {
                    "status": "completed",
                    "hash": "shared-hash",
                    "domain": "sre-triage",
                    "dataset": dataset,
                    "scenario": "CE-1-missing-evidence",
                    "playbook_code": "CE-1",
                    "model": "test-model",
                    "metrics": [
                        {
                            "high_level_metric": "Verification Quality",
                            "score": score,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    summarize(output_dir=tmp_path)

    with (tmp_path / "challenge_observability.csv").open(
        encoding="utf-8",
        newline="",
    ) as handle:
        rows = list(csv.DictReader(handle))
    ce1 = next(row for row in rows if row["challenge"] == "CE-1")

    assert ce1["n"] == "2"
    assert ce1["target_failures"] == "1"
