#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Evaluate NOA trajectories with evaluate_file. --dry-run makes no model calls."""

import argparse
import json
import os
import sys
from pathlib import Path

from stateful_evals_be import (
    LLMJudgeConfig,
    TemporalMetricOptions,
    evaluate_file,
    session_result_payload,
)
from stateful_evals_be.evaluation.trajectory_context_metrics import (
    resolve_trajectory_metric_codes,
)
from stateful_evals_be.integrations.files import load_trajectory_file
from stateful_evals_be.policy_loader import default_policy_path_for_domain

HERE = Path(__file__).resolve().parent
ENV_VARS = ("LLM_MODEL_NAME", "LLM_BASE_MODEL_URL", "LLM_API_KEY")
NOA_POLICY = default_policy_path_for_domain("noa")  # stateful_evals_be/policies/noa.md


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trajectory-dir", type=Path, default=HERE / "data")
    parser.add_argument("-n", "--limit", type=int, default=1, help="files to run")
    parser.add_argument("--metrics", default="groundedness,task_completion")
    parser.add_argument("--policy-file", type=Path, default=NOA_POLICY)
    parser.add_argument("--output-dir", type=Path, default=HERE / "output")
    parser.add_argument("--dry-run", action="store_true", help="make no model calls")
    args = parser.parse_args()

    folder = args.trajectory_dir.expanduser()
    files = sorted(
        folder.glob("trajectory_*.json"), key=lambda p: (p.stat().st_size, p.name)
    )
    files = files[: args.limit]
    if not files:
        sys.exit(f"No trajectory_*.json in {folder}. See quickstart/README.md.")
    if not args.policy_file.is_file():
        sys.exit(f"Policy file not found: {args.policy_file}")
    policy = args.policy_file.read_text(encoding="utf-8").strip()
    try:
        metrics = list(resolve_trajectory_metric_codes(args.metrics.split(",")))
    except ValueError as exc:
        sys.exit(str(exc))
    print(f"metrics={','.join(metrics)} policy={args.policy_file.name}")

    for path in files:  # check every file before any model call
        try:
            session_id, spans = load_trajectory_file(path)
        except ValueError as exc:
            sys.exit(f"{path}: {exc}")
        if args.dry_run:
            print(f"would evaluate {path.name}: {session_id} ({len(spans)} spans)")
    if args.dry_run:
        return

    if missing := [name for name in ENV_VARS if not os.environ.get(name)]:
        sys.exit(f"Set {', '.join(missing)}. See quickstart/README.md.")
    llm_config = LLMJudgeConfig(**{name: os.environ[name] for name in ENV_VARS})
    options = TemporalMetricOptions(trajectory_metrics=metrics)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        result = evaluate_file(
            path, llm_config=llm_config, options=options, policy_override=policy
        )
        payload = session_result_payload(result)
        out = args.output_dir / f"{path.stem}.result.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        statuses = " ".join(
            f"{m['metadata']['metric_code']}={m['status']}"
            for m in payload.get("trajectory_metrics", [])
        )
        print(
            f"{result.session_id} trajectory_score={result.trajectory_score} "
            f"{statuses} tokens={result.token_usage.total_tokens}"
            + (f" error={result.error}" if result.error else "")
        )


if __name__ == "__main__":
    main()
