#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Run stateful_evals_be on trajectory datasets and compare with reward labels.

This script reads trajectory JSON files, derives expected labels from
`reward_info.reward` (or top-level `reward`), evaluates corresponding session IDs
through TemporalMetricsProcessor, and reports whether:

    trajectory_score == expected_reward_label

Expected label mapping:
  - reward >= 0.5 -> 1
  - reward < 0.5 -> 0

Usage:
  python -m stateful_evals_be.scripts.run_reward_alignment
  python -m stateful_evals_be.scripts.run_reward_alignment --dry-run
  python -m stateful_evals_be.scripts.run_reward_alignment --max-files 20
"""

import argparse
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import statistics
from typing import Any, Dict, Iterable, List, Optional

# Ensure mdt_layer and MCE src are importable when running as a module/script.
SCRIPT_DIR = Path(__file__).resolve().parent
MDT_LAYER_DIR = SCRIPT_DIR.parent.parent
STATEFUL_EVALS_DIR = MDT_LAYER_DIR.parent
LOCAL_TRAJECTORIES_DIR = MDT_LAYER_DIR / "data" / "trajectories"
if str(MDT_LAYER_DIR) not in sys.path:
    sys.path.insert(0, str(MDT_LAYER_DIR))
MCE_SRC_CANDIDATES = [
    MDT_LAYER_DIR / "telemetry-hub" / "metrics_computation_engine" / "src",
    STATEFUL_EVALS_DIR / "telemetry-hub" / "metrics_computation_engine" / "src",
    STATEFUL_EVALS_DIR.parent / "telemetry-hub" / "metrics_computation_engine" / "src",
]
for mce_src in MCE_SRC_CANDIDATES:
    if mce_src.exists():
        if str(mce_src) not in sys.path:
            sys.path.insert(0, str(mce_src))
        break

LOGGER = logging.getLogger("reward_alignment")

from stateful_evals_be.policy_loader import (  # noqa: E402
    default_policy_path_for_domain,
    load_task_policy_text_map,
    resolve_policy_text,
)
from stateful_evals_be.evaluation.replay_scoring import (  # noqa: E402
    ReplayScoringProfile,
    available_profiles,
    parse_profile_list,
    rescore_session_result,
)

DEFAULT_TRAJECTORY_DIR_CANDIDATES = [
    LOCAL_TRAJECTORIES_DIR / "tau2_trajectories",
    LOCAL_TRAJECTORIES_DIR / "tau2_trajectories_airline",
    LOCAL_TRAJECTORIES_DIR / "tau2_trajectories_retail",
    LOCAL_TRAJECTORIES_DIR / "tau2_trajectories_telecom",
]


@dataclass
class TrajectoryCase:
    file_path: str
    trajectory_id: str
    task_id: str
    domain: str
    session_id: str
    reward: float
    expected_label: int
    num_spans: int


@dataclass
class ReplayArtifact:
    source_file: str
    evaluation_result: Dict[str, Any]
    eval_duration_seconds: Optional[float]
    original_predicted_label: Optional[int]


def _maybe_load_dotenv() -> None:
    """Load .env if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv()
    except Exception:
        # dotenv is optional for this runner.
        pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run stateful_evals_be on trajectory datasets and compare "
            "trajectory_score with reward_info.reward labels."
        )
    )
    parser.add_argument(
        "--trajectory-dirs",
        type=str,
        default=None,
        help=(
            "Comma-separated trajectory directories. "
            "Default: auto-discover built-in trajectory directories under "
            "stateful_evals/backend/data/trajectories."
        ),
    )
    parser.add_argument(
        "--replay-per-trajectory-dirs",
        type=str,
        default=None,
        help=(
            "Comma-separated directories containing saved per-trajectory JSON "
            "artifacts from earlier runs. Enables replay mode (no live eval)."
        ),
    )
    parser.add_argument(
        "--replay-profiles",
        type=str,
        default="current",
        help=(
            "Comma-separated replay scoring profiles to compare in replay mode. "
            "Default: current"
        ),
    )
    parser.add_argument(
        "--list-replay-profiles",
        action="store_true",
        help="List built-in replay profiles and exit.",
    )
    parser.add_argument(
        "--session-id-regex",
        type=str,
        default=None,
        help=(
            "Optional regex filter applied to session IDs after loading cases. "
            "Useful for targeted trajectory unit tests."
        ),
    )
    parser.add_argument(
        "--glob-pattern",
        type=str,
        default="trajectory_*.json",
        help="File glob pattern within each trajectory directory (default: trajectory_*.json)",
    )
    parser.add_argument(
        "--default-domain",
        type=str,
        default="airline",
        help="Fallback domain if app_name cannot be parsed (default: airline)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=None,
        help="Max trajectory files to load per directory (default: all)",
    )
    parser.add_argument(
        "--max-spans",
        type=int,
        default=None,
        help=(
            "Restrict to traces with <= this many spans. "
            "Use to skip long traces that may timeout."
        ),
    )
    parser.add_argument(
        "--max-evals",
        type=int,
        default=None,
        help="Max trajectories to evaluate after filtering (default: all).",
    )
    parser.add_argument(
        "--balance-expected-labels",
        action="store_true",
        help=(
            "Downsample selected cases so expected_label=0 and expected_label=1 "
            "are equally represented. Applied after filtering and with --max-evals."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only discover trajectories and expected labels, do not evaluate.",
    )
    parser.add_argument(
        "--lengths-only",
        action="store_true",
        help="Print trace lengths and exit without running evaluation.",
    )
    parser.add_argument(
        "--show-lengths",
        action="store_true",
        help="Print per-trace lengths before evaluation.",
    )
    parser.add_argument(
        "--lengths-limit",
        type=int,
        default=30,
        help="Max lines to print for --show-lengths (default: 30, <=0 means all).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=20,
        help="Sessions per processor.run_evaluation call (default: 20)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=3,
        help="Parallel workers inside TemporalMetricsProcessor (default: 3)",
    )
    parser.add_argument(
        "--parallel-evals",
        type=int,
        default=3,
        help=(
            "How many trajectories to evaluate concurrently in this runner "
            "(default: 3)."
        ),
    )
    parser.add_argument(
        "--fatality-threshold",
        type=float,
        default=0.5,
        help="Fatality threshold passed to TemporalMetricOptions (default: 0.5)",
    )
    parser.add_argument(
        "--llm-model-name",
        type=str,
        default=os.getenv("LLM_MODEL_NAME", "gpt-4o"),
        help="Judge model name (default: $LLM_MODEL_NAME or gpt-4o)",
    )
    parser.add_argument(
        "--llm-base-url",
        type=str,
        default=os.getenv("LLM_BASE_MODEL_URL", "https://api.openai.com/v1"),
        help="Judge base URL (default: $LLM_BASE_MODEL_URL or OpenAI)",
    )
    parser.add_argument(
        "--llm-api-key",
        type=str,
        default=os.getenv("LLM_API_KEY", "sk-..."),
        help="Judge API key (default: $LLM_API_KEY)",
    )
    parser.add_argument(
        "--report-json",
        type=str,
        default=None,
        help="Optional output path for JSON report (default: auto timestamped path)",
    )
    parser.add_argument(
        "--per-trajectory-dir",
        type=str,
        default=None,
        help=(
            "Directory for per-trajectory JSON artifacts. "
            "Default: <report_stem>_per_trajectory next to --report-json."
        ),
    )
    parser.add_argument(
        "--no-save-per-trajectory",
        action="store_true",
        help="Disable saving per-trajectory JSON artifacts.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print all cases (not only mismatches/errors).",
    )
    parser.add_argument(
        "--policy-file",
        type=str,
        default=None,
        help=(
            "Optional fallback policy file for all tasks. "
            "If omitted, built-in policy defaults are used for known domains."
        ),
    )
    parser.add_argument(
        "--task-policy-map",
        type=str,
        default=None,
        help=(
            "Optional JSON file mapping task IDs (for example: task11) to policy "
            "entries. Entries support strings (file path or inline text) or "
            "{policy_file|policy_text} objects."
        ),
    )
    parser.add_argument(
        "--session-prefix",
        type=str,
        default=None,
        help=(
            "Override the session ID prefix. By default, session IDs are "
            "constructed as 'tau2-{domain}_{trajectory_id}'. Use this to match "
            "a custom import prefix (e.g. 'noa-trip-planner' for NOA imports)."
        ),
    )
    parser.add_argument(
        "--use-server",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--temporal-evals-url",
        type=str,
        default=None,
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    if args.max_evals is not None and args.max_evals <= 0:
        parser.error("--max-evals must be > 0")
    if args.parallel_evals <= 0:
        parser.error("--parallel-evals must be > 0")
    if args.use_server or args.temporal_evals_url:
        parser.error(
            "The standalone evaluation server is retired. Remove --use-server and "
            "--temporal-evals-url to evaluate in-process. Span retrieval uses the "
            "API library's database settings; metric computation uses the MCE library."
        )
    if args.list_replay_profiles:
        return args
    if args.replay_per_trajectory_dirs:
        try:
            parse_profile_list(args.replay_profiles)
        except ValueError as exc:
            parser.error(str(exc))
    if args.session_id_regex:
        try:
            re.compile(args.session_id_regex)
        except re.error as exc:
            parser.error(f"Invalid --session-id-regex: {exc}")
    return args


def _resolve_trajectory_dirs(raw_dirs: Optional[str]) -> List[Path]:
    if raw_dirs:
        resolved: List[Path] = []
        for piece in [p.strip() for p in raw_dirs.split(",") if p.strip()]:
            path = Path(piece).expanduser().resolve()
            if not path.exists() or not path.is_dir():
                raise FileNotFoundError(f"Trajectory directory not found: {path}")
            resolved.append(path)
        return resolved

    discovered = [
        path
        for path in DEFAULT_TRAJECTORY_DIR_CANDIDATES
        if path.exists() and path.is_dir()
    ]
    if not discovered:
        raise FileNotFoundError(
            "No default trajectory directories found. "
            f"Tried: {[str(p) for p in DEFAULT_TRAJECTORY_DIR_CANDIDATES]}"
        )
    return discovered


def _resolve_replay_dirs(raw_dirs: str) -> List[Path]:
    resolved: List[Path] = []
    for piece in [p.strip() for p in raw_dirs.split(",") if p.strip()]:
        path = Path(piece).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise FileNotFoundError(f"Replay directory not found: {path}")
        resolved.append(path)
    if not resolved:
        raise FileNotFoundError("No replay directories provided.")
    return resolved


def _load_replay_cases(
    replay_dirs: List[Path],
    max_files: Optional[int],
    max_spans: Optional[int],
    session_id_regex: Optional[str],
) -> tuple[List[TrajectoryCase], Dict[str, ReplayArtifact]]:
    session_filter = re.compile(session_id_regex) if session_id_regex else None
    cases: List[TrajectoryCase] = []
    artifacts: Dict[str, ReplayArtifact] = {}
    seen_paths = set()

    for directory in replay_dirs:
        paths = sorted(
            path for path in directory.glob("*.json") if path.name != "index.json"
        )
        if max_files is not None:
            paths = paths[:max_files]

        for path in paths:
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)

            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                LOGGER.warning(
                    "Skipping replay artifact %s (json read error: %s)", path, exc
                )
                continue

            session_id = str(payload.get("session_id") or "").strip()
            if not session_id:
                LOGGER.warning("Skipping replay artifact %s (missing session_id)", path)
                continue
            if session_filter and not session_filter.search(session_id):
                continue

            num_spans = int(payload.get("num_spans") or 0)
            if max_spans is not None and num_spans > max_spans:
                continue

            if session_id in artifacts:
                LOGGER.warning(
                    "Duplicate replay session_id %s detected; keeping first artifact and skipping %s",
                    session_id,
                    path,
                )
                continue

            reward_raw = payload.get("reward")
            reward_float = 1.0 if payload.get("expected_label") else 0.0
            if reward_raw is not None:
                try:
                    reward_float = float(reward_raw)
                except (TypeError, ValueError):
                    pass

            expected_raw = payload.get("expected_label")
            expected_label = _reward_to_label(reward_float)
            if expected_raw is not None:
                try:
                    expected_label = int(expected_raw)
                except (TypeError, ValueError):
                    expected_label = _reward_to_label(reward_float)

            trajectory_id = str(payload.get("trajectory_id") or session_id)
            task_id = str(payload.get("task_id") or "task_unknown")
            domain = str(payload.get("domain") or "unknown")
            trajectory_file = str(payload.get("trajectory_file") or path)

            case = TrajectoryCase(
                file_path=trajectory_file,
                trajectory_id=trajectory_id,
                task_id=task_id,
                domain=domain,
                session_id=session_id,
                reward=reward_float,
                expected_label=expected_label,
                num_spans=num_spans,
            )
            cases.append(case)
            artifacts[session_id] = ReplayArtifact(
                source_file=str(path),
                evaluation_result=payload.get("evaluation_result") or {},
                eval_duration_seconds=payload.get("eval_duration_seconds"),
                original_predicted_label=payload.get("predicted_label"),
            )

    cases.sort(key=lambda case: case.session_id)
    return cases, artifacts


def _iter_chunks(items: List[str], chunk_size: int) -> Iterable[List[str]]:
    if chunk_size <= 0:
        raise ValueError("--chunk-size must be > 0")
    for idx in range(0, len(items), chunk_size):
        yield items[idx : idx + chunk_size]


def _parse_domain(app_name: str, default_domain: str) -> str:
    if app_name.startswith("tau2-bench-"):
        candidate = app_name.split("tau2-bench-", 1)[1].strip().lower()
        if candidate:
            return candidate
    return default_domain


def _reward_to_label(reward: float) -> int:
    return 1 if float(reward) >= 0.5 else 0


def _normalize_task_id(raw_task_id: Any, file_path: Path) -> str:
    if isinstance(raw_task_id, int):
        return f"task{raw_task_id}"
    if isinstance(raw_task_id, str) and raw_task_id.strip():
        value = raw_task_id.strip()
        return value if value.startswith("task") else f"task{value}"

    match = re.search(r"trajectory_(task[^_]+)_", file_path.name)
    if match:
        return match.group(1)
    return "task_unknown"


def _resolve_policy_for_case(
    *,
    case: TrajectoryCase,
    fallback_policy_text: Optional[str],
    task_policy_text_map: Dict[str, str],
) -> str:
    if case.task_id in task_policy_text_map:
        return task_policy_text_map[case.task_id]

    if fallback_policy_text:
        return fallback_policy_text

    # For known domains, use copied built-in policies under stateful_evals_be/policies.
    # For unknown/future domains, require explicit policy input.
    return resolve_policy_text(domain=case.domain)


def _load_case_from_file(
    file_path: Path,
    default_domain: str,
    session_prefix: Optional[str] = None,
) -> Optional[TrajectoryCase]:
    try:
        with open(file_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception as exc:
        LOGGER.warning("Skipping %s (json read error: %s)", file_path, exc)
        return None

    trajectory_id = data.get("id")
    if not trajectory_id:
        LOGGER.warning("Skipping %s (missing trajectory id)", file_path)
        return None

    reward = data.get("reward")
    if reward is None:
        reward = (data.get("reward_info") or {}).get("reward")
    if reward is None:
        LOGGER.warning("Skipping %s (missing reward)", file_path)
        return None

    try:
        reward_float = float(reward)
    except (TypeError, ValueError):
        LOGGER.warning("Skipping %s (invalid reward=%s)", file_path, reward)
        return None

    spans = data.get("spans") or []
    app_name = ""
    if spans and isinstance(spans[0], dict):
        app_name = str(spans[0].get("app_name") or "")
    domain = _parse_domain(app_name, default_domain=default_domain)
    if session_prefix is not None:
        session_id = f"{session_prefix}_{trajectory_id}"
    else:
        session_id = f"tau2-{domain}_{trajectory_id}"
    task_id = _normalize_task_id(data.get("task_id"), file_path=file_path)

    return TrajectoryCase(
        file_path=str(file_path),
        trajectory_id=str(trajectory_id),
        task_id=task_id,
        domain=domain,
        session_id=session_id,
        reward=reward_float,
        expected_label=_reward_to_label(reward_float),
        num_spans=len(spans),
    )


def load_cases(
    trajectory_dirs: List[Path],
    glob_pattern: str,
    max_files: Optional[int],
    default_domain: str,
    session_prefix: Optional[str] = None,
) -> List[TrajectoryCase]:
    all_paths: List[Path] = []
    seen_paths = set()

    for directory in trajectory_dirs:
        paths = sorted(directory.glob(glob_pattern))
        if max_files is not None:
            paths = paths[:max_files]
        for path in paths:
            resolved = path.resolve()
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            all_paths.append(path)

    cases: List[TrajectoryCase] = []
    for path in all_paths:
        case = _load_case_from_file(
            path,
            default_domain=default_domain,
            session_prefix=session_prefix,
        )
        if case is not None:
            cases.append(case)

    return sorted(cases, key=lambda case: case.session_id)


def _build_llm_config(args: argparse.Namespace):
    from metrics_computation_engine.models.requests import LLMJudgeConfig

    return LLMJudgeConfig(
        LLM_MODEL_NAME=args.llm_model_name,
        LLM_BASE_MODEL_URL=args.llm_base_url,
        LLM_API_KEY=args.llm_api_key,
    )


def _evaluate_cases(
    cases: List[TrajectoryCase],
    args: argparse.Namespace,
) -> Dict[str, Any]:
    from stateful_evals_be.evaluation.processor import TemporalMetricsProcessor
    from stateful_evals_be.models.requests import TemporalMetricOptions

    llm_config = _build_llm_config(args)
    task_policy_text_map = load_task_policy_text_map(args.task_policy_map)
    fallback_policy_text: Optional[str] = None
    if args.policy_file:
        # Domain is intentionally left as "unknown" when explicit policy file is given.
        # resolve_policy_text validates file existence and content.
        fallback_policy_text = resolve_policy_text(
            domain="unknown",
            policy_file=args.policy_file,
        )

    options = TemporalMetricOptions(
        use_fatal_mode=True,
        fatality_threshold=args.fatality_threshold,
        batch_size=args.batch_size,
    )

    print("Metric computation: MCE library (in-process)")

    def _make_processor() -> TemporalMetricsProcessor:
        return TemporalMetricsProcessor(
            llm_config=llm_config,
            options=options,
        )

    def _evaluate_case(
        case: TrajectoryCase,
        processor: TemporalMetricsProcessor,
    ) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            policy_text = _resolve_policy_for_case(
                case=case,
                fallback_policy_text=fallback_policy_text,
                task_policy_text_map=task_policy_text_map,
            )
        except Exception as exc:
            return None, f"Policy resolution failed for task '{case.task_id}': {exc}"

        try:
            result = processor.evaluate_session(
                case.session_id,
                policy_override=policy_text,
            )
        except Exception as exc:
            return None, str(exc)
        finally:
            processor.close()
        if result.error:
            return None, result.error
        return result.model_dump(), None

    results_by_session: Dict[str, Dict[str, Any]] = {}
    errors_by_session: Dict[str, str] = {}
    timing_by_session: Dict[str, float] = {}
    total = len(cases)
    matches = 0
    mismatches = 0
    errors = 0
    started = time.time()

    print(f"\nPer-trajectory progress (parallel={args.parallel_evals}):")

    def _record_progress(
        idx: int,
        case: TrajectoryCase,
        result_dict: Optional[Dict[str, Any]],
        error_text: Optional[str],
        eval_duration: float = 0.0,
    ) -> None:
        nonlocal matches, mismatches, errors
        session_id = case.session_id
        timing_by_session[session_id] = eval_duration
        if error_text:
            errors_by_session[session_id] = error_text
            errors += 1
            evaluated = matches + mismatches
            running_accuracy = (matches / evaluated) if evaluated > 0 else 0.0
            elapsed = time.time() - started
            print(
                f"[{idx}/{total}] ! {session_id} expected={case.expected_label} "
                f"error={error_text} running_acc={running_accuracy:.4f} "
                f"(match={matches} mismatch={mismatches} errors={errors}) "
                f"elapsed={elapsed:.1f}s eval_time={eval_duration:.1f}s"
            )
            return

        result_payload = result_dict or {}
        results_by_session[session_id] = result_payload
        predicted = result_payload.get("trajectory_score")
        is_match = predicted == case.expected_label
        if is_match:
            matches += 1
            symbol = "✓"
        else:
            mismatches += 1
            symbol = "✗"

        evaluated = matches + mismatches
        running_accuracy = (matches / evaluated) if evaluated > 0 else 0.0
        elapsed = time.time() - started
        traj_tokens = (result_payload.get("token_usage") or {}).get("total_tokens", 0)
        print(
            f"[{idx}/{total}] {symbol} {session_id} expected={case.expected_label} "
            f"got={predicted} running_acc={running_accuracy:.4f} "
            f"(match={matches} mismatch={mismatches} errors={errors}) "
            f"elapsed={elapsed:.1f}s eval_time={eval_duration:.1f}s "
            f"tokens={traj_tokens:,}"
        )

    processor = _make_processor()

    if args.parallel_evals == 1:
        for idx, case in enumerate(cases, start=1):
            t0 = time.time()
            result_dict, error_text = _evaluate_case(case, processor=processor)
            eval_duration = time.time() - t0
            _record_progress(
                idx=idx,
                case=case,
                result_dict=result_dict,
                error_text=error_text,
                eval_duration=eval_duration,
            )
    else:

        def _parallel_task(
            case: TrajectoryCase,
        ) -> tuple[TrajectoryCase, Optional[Dict[str, Any]], Optional[str], float]:
            t0 = time.time()
            result_dict, error_text = _evaluate_case(case, processor=processor)
            eval_duration = time.time() - t0
            return case, result_dict, error_text, eval_duration

        with ThreadPoolExecutor(max_workers=args.parallel_evals) as executor:
            future_to_case = {
                executor.submit(_parallel_task, case): case for case in cases
            }
            for idx, future in enumerate(as_completed(future_to_case), start=1):
                eval_duration = 0.0
                try:
                    case, result_dict, error_text, eval_duration = future.result()
                except Exception as exc:
                    case = future_to_case[future]
                    result_dict = None
                    error_text = str(exc)
                _record_progress(
                    idx=idx,
                    case=case,
                    result_dict=result_dict,
                    error_text=error_text,
                    eval_duration=eval_duration,
                )

    return {
        "results_by_session": results_by_session,
        "errors_by_session": errors_by_session,
        "timing_by_session": timing_by_session,
    }


def _evaluate_cases_via_replay(
    *,
    cases: List[TrajectoryCase],
    replay_artifacts: Dict[str, ReplayArtifact],
    profile: ReplayScoringProfile,
) -> Dict[str, Any]:
    """Replay scoring over saved per-trajectory artifacts."""
    total = len(cases)
    matches = 0
    mismatches = 0
    errors = 0
    started = time.time()

    results_by_session: Dict[str, Dict[str, Any]] = {}
    errors_by_session: Dict[str, str] = {}
    timing_by_session: Dict[str, float] = {}

    print(f"\nReplay progress (profile={profile.name}, cases={total}):")
    for idx, case in enumerate(cases, start=1):
        artifact = replay_artifacts.get(case.session_id)
        if artifact is None:
            errors += 1
            error_text = "Missing replay artifact for session"
            errors_by_session[case.session_id] = error_text
            evaluated = matches + mismatches
            running_accuracy = (matches / evaluated) if evaluated > 0 else 0.0
            elapsed = time.time() - started
            print(
                f"[{idx}/{total}] ! {case.session_id} expected={case.expected_label} "
                f"error={error_text} running_acc={running_accuracy:.4f} "
                f"(match={matches} mismatch={mismatches} errors={errors}) "
                f"elapsed={elapsed:.1f}s"
            )
            continue

        source_result = artifact.evaluation_result or {}
        outcome = rescore_session_result(source_result, profile=profile)
        replay_result = deepcopy(source_result)
        replay_result["trajectory_score"] = outcome.predicted_label
        replay_result["unsatisfied_intents"] = outcome.adjusted_unsatisfied_intents
        replay_result["fatal_failures"] = outcome.adjusted_fatal_failures
        replay_result["minor_failures"] = outcome.adjusted_minor_failures
        replay_result["quality_gate_failures"] = outcome.quality_gate_failures
        replay_result["replay_profile"] = profile.name
        replay_result["replay_source_file"] = artifact.source_file
        replay_result["replay_original_predicted_label"] = (
            artifact.original_predicted_label
        )
        replay_result["replay_downgraded_fatal_failures"] = (
            outcome.downgraded_fatal_failures
        )
        replay_result["replay_downgraded_fatal_count"] = len(
            outcome.downgraded_fatal_failures
        )

        results_by_session[case.session_id] = replay_result
        if artifact.eval_duration_seconds is not None:
            timing_by_session[case.session_id] = artifact.eval_duration_seconds
        elif source_result.get("eval_duration_seconds") is not None:
            timing_by_session[case.session_id] = source_result.get(
                "eval_duration_seconds"
            )

        is_match = outcome.predicted_label == case.expected_label
        if is_match:
            matches += 1
            symbol = "✓"
        else:
            mismatches += 1
            symbol = "✗"

        evaluated = matches + mismatches
        running_accuracy = (matches / evaluated) if evaluated > 0 else 0.0
        elapsed = time.time() - started
        quality_gate_text = (
            ",".join(outcome.quality_gate_failures)
            if outcome.quality_gate_failures
            else "-"
        )
        print(
            f"[{idx}/{total}] {symbol} {case.session_id} expected={case.expected_label} "
            f"got={outcome.predicted_label} running_acc={running_accuracy:.4f} "
            f"(match={matches} mismatch={mismatches} errors={errors}) "
            f"elapsed={elapsed:.1f}s qg={quality_gate_text} "
            f"downgraded={len(outcome.downgraded_fatal_failures)}"
        )

    return {
        "results_by_session": results_by_session,
        "errors_by_session": errors_by_session,
        "timing_by_session": timing_by_session,
    }


def _summarize(
    cases: List[TrajectoryCase],
    eval_output: Dict[str, Any],
) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    domain_stats: Dict[str, Dict[str, int]] = {}

    def ensure_domain(domain: str) -> Dict[str, int]:
        if domain not in domain_stats:
            domain_stats[domain] = {
                "total": 0,
                "matches": 0,
                "mismatches": 0,
                "errors": 0,
            }
        return domain_stats[domain]

    results_by_session: Dict[str, Dict[str, Any]] = eval_output["results_by_session"]
    errors_by_session: Dict[str, str] = eval_output["errors_by_session"]
    timing_by_session: Dict[str, float] = eval_output.get("timing_by_session", {})

    for case in cases:
        stats = ensure_domain(case.domain)
        stats["total"] += 1

        result = results_by_session.get(case.session_id)
        error_text = errors_by_session.get(case.session_id)
        predicted_label: Optional[int] = None
        match: Optional[bool] = None

        if error_text:
            stats["errors"] += 1
        elif result is not None:
            predicted_label = result.get("trajectory_score")
            match = predicted_label == case.expected_label
            if match:
                stats["matches"] += 1
            else:
                stats["mismatches"] += 1
        else:
            error_text = "No result returned for session"
            stats["errors"] += 1

        token_usage = (result or {}).get("token_usage") or {}
        rows.append(
            {
                **asdict(case),
                "predicted_label": predicted_label,
                "match": match,
                "error": error_text,
                "unsatisfied_intents": (result or {}).get("unsatisfied_intents"),
                "intent_states": (result or {}).get("intent_states") or [],
                "fatal_failures": len((result or {}).get("fatal_failures") or []),
                "minor_failures": len((result or {}).get("minor_failures") or []),
                "quality_gate_failures": (result or {}).get("quality_gate_failures")
                or [],
                "quality_gate_reasoning": (result or {}).get("quality_gate_reasoning")
                or {},
                "replay_downgraded_fatal_count": (result or {}).get(
                    "replay_downgraded_fatal_count"
                ),
                "total_failures": (result or {}).get("total_failures"),
                "token_usage": token_usage,
                "eval_duration_seconds": timing_by_session.get(case.session_id),
            }
        )

    total = len(cases)
    matches = sum(1 for row in rows if row["match"] is True)
    mismatches = sum(1 for row in rows if row["match"] is False)
    errors = sum(1 for row in rows if row["error"])
    evaluated = matches + mismatches
    accuracy = (matches / evaluated) if evaluated > 0 else 0.0

    agg_prompt = sum(
        int((row.get("token_usage") or {}).get("prompt_tokens", 0)) for row in rows
    )
    agg_completion = sum(
        int((row.get("token_usage") or {}).get("completion_tokens", 0)) for row in rows
    )
    agg_total = sum(
        int((row.get("token_usage") or {}).get("total_tokens", 0)) for row in rows
    )
    agg_mce_total = sum(
        int((row.get("token_usage") or {}).get("mce_total_tokens", 0)) for row in rows
    )
    agg_fatality_total = sum(
        int((row.get("token_usage") or {}).get("fatality_total_tokens", 0))
        for row in rows
    )

    eval_durations = [
        row["eval_duration_seconds"]
        for row in rows
        if row.get("eval_duration_seconds") is not None
    ]
    timing_stats: Dict[str, Any] = {}
    if eval_durations:
        timing_stats = {
            "total_seconds": round(sum(eval_durations), 2),
            "mean_seconds": round(statistics.mean(eval_durations), 2),
            "median_seconds": round(statistics.median(eval_durations), 2),
            "min_seconds": round(min(eval_durations), 2),
            "max_seconds": round(max(eval_durations), 2),
            "count": len(eval_durations),
        }

    return {
        "summary": {
            "total_cases": total,
            "evaluated_cases": evaluated,
            "matches": matches,
            "mismatches": mismatches,
            "errors": errors,
            "accuracy": accuracy,
            "domain_stats": domain_stats,
            "token_usage": {
                "prompt_tokens": agg_prompt,
                "completion_tokens": agg_completion,
                "total_tokens": agg_total,
                "mce_total_tokens": agg_mce_total,
                "fatality_total_tokens": agg_fatality_total,
            },
            "eval_timing": timing_stats,
        },
        "rows": rows,
    }


def _default_report_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_dir = MDT_LAYER_DIR / "stateful_evals_be_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / f"reward_alignment_{timestamp}.json"


def _default_per_trajectory_dir(report_path: Path) -> Path:
    return report_path.parent / f"{report_path.stem}_per_trajectory"


def _safe_file_stem(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return safe or "session"


def _write_per_trajectory_results(
    *,
    output_dir: Path,
    cases: List[TrajectoryCase],
    eval_output: Dict[str, Any],
    report_rows: List[Dict[str, Any]],
) -> int:
    results_by_session: Dict[str, Dict[str, Any]] = eval_output["results_by_session"]
    errors_by_session: Dict[str, str] = eval_output["errors_by_session"]
    timing_by_session: Dict[str, float] = eval_output.get("timing_by_session", {})
    rows_by_session = {row["session_id"]: row for row in report_rows}

    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    index_rows: List[Dict[str, Any]] = []

    for case in cases:
        row = rows_by_session.get(case.session_id, {})
        error_text = errors_by_session.get(case.session_id) or row.get("error")
        per_case_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": case.session_id,
            "trajectory_id": case.trajectory_id,
            "task_id": case.task_id,
            "trajectory_file": case.file_path,
            "domain": case.domain,
            "reward": case.reward,
            "expected_label": case.expected_label,
            "predicted_label": row.get("predicted_label"),
            "match": row.get("match"),
            "error": error_text,
            "num_spans": case.num_spans,
            "eval_duration_seconds": timing_by_session.get(case.session_id),
            "summary": {
                "unsatisfied_intents": row.get("unsatisfied_intents"),
                "intent_states": row.get("intent_states") or [],
                "fatal_failures": row.get("fatal_failures"),
                "minor_failures": row.get("minor_failures"),
                "quality_gate_failures": row.get("quality_gate_failures") or [],
                "quality_gate_reasoning": row.get("quality_gate_reasoning") or {},
                "replay_downgraded_fatal_count": row.get(
                    "replay_downgraded_fatal_count"
                ),
                "total_failures": row.get("total_failures"),
                "token_usage": row.get("token_usage"),
            },
            "evaluation_result": results_by_session.get(case.session_id),
        }

        file_name = f"{_safe_file_stem(case.session_id)}.json"
        out_path = output_dir / file_name
        with open(out_path, "w", encoding="utf-8") as handle:
            json.dump(per_case_payload, handle, indent=2)
        written += 1

        index_rows.append(
            {
                "session_id": case.session_id,
                "trajectory_id": case.trajectory_id,
                "task_id": case.task_id,
                "file_name": file_name,
                "match": row.get("match"),
                "error": error_text,
            }
        )

    index_payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": written,
        "results": index_rows,
    }
    with open(output_dir / "index.json", "w", encoding="utf-8") as handle:
        json.dump(index_payload, handle, indent=2)

    return written


def _length_stats(cases: List[TrajectoryCase]) -> Dict[str, Any]:
    lengths = [case.num_spans for case in cases]
    if not lengths:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "p90": None,
            "p95": None,
        }

    sorted_lengths = sorted(lengths)

    def percentile(p: float) -> int:
        if not sorted_lengths:
            return 0
        idx = int(round((len(sorted_lengths) - 1) * p))
        return sorted_lengths[idx]

    return {
        "count": len(sorted_lengths),
        "min": sorted_lengths[0],
        "max": sorted_lengths[-1],
        "mean": statistics.mean(sorted_lengths),
        "median": statistics.median(sorted_lengths),
        "p90": percentile(0.90),
        "p95": percentile(0.95),
    }


def _print_lengths(cases: List[TrajectoryCase], limit: int = 30) -> None:
    rows = sorted(cases, key=lambda case: case.num_spans, reverse=True)
    print("\nTrace lengths (sorted by spans desc):")
    if limit > 0:
        rows = rows[:limit]
    for case in rows:
        print(
            f"  spans={case.num_spans:3d} "
            f"session={case.session_id} "
            f"reward={case.reward:.1f} "
            f"file={Path(case.file_path).name}"
        )


def _print_summary(
    summary: Dict[str, Any], rows: List[Dict[str, Any]], verbose: bool
) -> None:
    print("\n" + "=" * 90)
    print("Reward Alignment Report")
    print("=" * 90)
    print(f"Total cases:      {summary['total_cases']}")
    print(f"Evaluated cases:  {summary['evaluated_cases']}")
    print(f"Matches:          {summary['matches']}")
    print(f"Mismatches:       {summary['mismatches']}")
    print(f"Errors:           {summary['errors']}")
    print(f"Accuracy:         {summary['accuracy']:.4f}")

    token_usage = summary.get("token_usage") or {}
    total_tok = token_usage.get("total_tokens", 0)
    mce_tok = token_usage.get("mce_total_tokens", 0)
    fat_tok = token_usage.get("fatality_total_tokens", 0)
    print("\nToken usage (all LLM calls):")
    print(f"  Prompt tokens:     {token_usage.get('prompt_tokens', 0):,}")
    print(f"  Completion tokens: {token_usage.get('completion_tokens', 0):,}")
    print(f"  Total tokens:      {total_tok:,}")
    print(f"    MCE span metrics:     {mce_tok:,}")
    print(f"    Fatality analysis:    {fat_tok:,}")

    eval_timing = summary.get("eval_timing") or {}
    if eval_timing:
        print("\nEvaluation timing (per trajectory):")
        print(f"  Total:   {eval_timing['total_seconds']:.1f}s")
        print(f"  Mean:    {eval_timing['mean_seconds']:.1f}s")
        print(f"  Median:  {eval_timing['median_seconds']:.1f}s")
        print(f"  Min:     {eval_timing['min_seconds']:.1f}s")
        print(f"  Max:     {eval_timing['max_seconds']:.1f}s")

    print("\nPer-domain:")
    for domain, stats in sorted(summary["domain_stats"].items()):
        evaluated = stats["matches"] + stats["mismatches"]
        domain_acc = (stats["matches"] / evaluated) if evaluated > 0 else 0.0
        print(
            f"  {domain}: total={stats['total']} "
            f"match={stats['matches']} mismatch={stats['mismatches']} "
            f"errors={stats['errors']} acc={domain_acc:.4f}"
        )

    print("\nCase results:")
    for row in rows:
        if not verbose and row["match"] is True and not row["error"]:
            continue
        status = "MATCH" if row["match"] is True else "MISMATCH"
        if row["error"]:
            status = "ERROR"
        duration = row.get("eval_duration_seconds")
        duration_str = f" time={duration:.1f}s" if duration is not None else ""
        quality_gate = row.get("quality_gate_failures") or []
        quality_gate_text = f" qg={','.join(quality_gate)}" if quality_gate else ""
        replay_downgraded = row.get("replay_downgraded_fatal_count")
        replay_text = (
            f" downgraded={replay_downgraded}" if replay_downgraded is not None else ""
        )
        print(
            f"  [{status}] {row['session_id']} "
            f"expected={row['expected_label']} predicted={row['predicted_label']} "
            f"unsatisfied={row['unsatisfied_intents']} "
            f"fatal={row['fatal_failures']} minor={row['minor_failures']}"
            f"{quality_gate_text}{replay_text}{duration_str}"
        )
        if row["error"]:
            print(f"    error: {row['error']}")


def _filter_cases_by_session_regex(
    cases: List[TrajectoryCase],
    session_id_regex: Optional[str],
) -> tuple[List[TrajectoryCase], int]:
    if not session_id_regex:
        return cases, 0
    pattern = re.compile(session_id_regex)
    filtered = [case for case in cases if pattern.search(case.session_id)]
    removed = len(cases) - len(filtered)
    return filtered, removed


def _select_balanced_cases_by_expected_label(
    cases: List[TrajectoryCase],
    max_evals: Optional[int],
) -> tuple[List[TrajectoryCase], Dict[str, int]]:
    expected_zero = [case for case in cases if case.expected_label == 0]
    expected_one = [case for case in cases if case.expected_label == 1]
    expected_other = len(cases) - len(expected_zero) - len(expected_one)

    requested_total = max_evals if max_evals is not None else len(cases)
    requested_even_total = requested_total - (requested_total % 2)
    requested_pairs = requested_even_total // 2
    available_pairs = min(len(expected_zero), len(expected_one))
    selected_pairs = min(requested_pairs, available_pairs)

    selected = expected_zero[:selected_pairs] + expected_one[:selected_pairs]
    selected.sort(key=lambda case: case.session_id)

    stats = {
        "requested_total": requested_total,
        "requested_even_total": requested_even_total,
        "requested_pairs": requested_pairs,
        "available_zero": len(expected_zero),
        "available_one": len(expected_one),
        "available_other": expected_other,
        "selected_zero": selected_pairs,
        "selected_one": selected_pairs,
        "selected_total": len(selected),
    }
    return selected, stats


def main() -> None:
    _maybe_load_dotenv()

    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    # Suppress LiteLLM's "Give Feedback / Get Help" banner that prints on
    # every completion call and every caught-and-retried exception.
    try:
        import litellm

        litellm.suppress_debug_info = True
    except ImportError:
        pass
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    if args.list_replay_profiles:
        print("Available replay profiles:")
        for name, profile in sorted(available_profiles().items()):
            print(f"  - {name}: {profile.description}")
        return

    replay_mode = bool(args.replay_per_trajectory_dirs)
    replay_dirs: List[Path] = []
    replay_artifacts: Dict[str, ReplayArtifact] = {}
    replay_profiles: List[ReplayScoringProfile] = []
    trajectory_dirs: List[Path] = []

    if replay_mode:
        replay_dirs = _resolve_replay_dirs(args.replay_per_trajectory_dirs or "")
        replay_profiles = parse_profile_list(args.replay_profiles)
        cases, replay_artifacts = _load_replay_cases(
            replay_dirs=replay_dirs,
            max_files=args.max_files,
            max_spans=None,
            session_id_regex=args.session_id_regex,
        )
    else:
        trajectory_dirs = _resolve_trajectory_dirs(args.trajectory_dirs)
        cases = load_cases(
            trajectory_dirs=trajectory_dirs,
            glob_pattern=args.glob_pattern,
            max_files=args.max_files,
            default_domain=args.default_domain,
            session_prefix=args.session_prefix,
        )
        cases, session_filtered_out = _filter_cases_by_session_regex(
            cases,
            session_id_regex=args.session_id_regex,
        )
        if session_filtered_out:
            print(f"Filtered out {session_filtered_out} case(s) by --session-id-regex.")

    if not cases:
        print("No trajectory cases found.")
        return

    all_cases_count = len(cases)
    filtered_out = 0
    if args.max_spans is not None:
        cases = [case for case in cases if case.num_spans <= args.max_spans]
        filtered_out = all_cases_count - len(cases)
        if not cases:
            print(
                f"All {all_cases_count} cases filtered out by --max-spans={args.max_spans}."
            )
            return

    max_eval_filtered_out = 0
    balanced_selection_stats: Optional[Dict[str, int]] = None
    if args.balance_expected_labels:
        before_count = len(cases)
        cases, balanced_selection_stats = _select_balanced_cases_by_expected_label(
            cases=cases,
            max_evals=args.max_evals,
        )
        max_eval_filtered_out = before_count - len(cases)
        if not cases:
            print(
                "No trajectory cases remain after --balance-expected-labels. "
                "Need at least one expected_label=0 and one expected_label=1 case."
            )
            return
    elif args.max_evals is not None and len(cases) > args.max_evals:
        max_eval_filtered_out = len(cases) - args.max_evals
        cases = cases[: args.max_evals]

    if replay_mode:
        print(
            f"Discovered {len(cases)} replay trajectory cases from "
            f"{len(replay_dirs)} directory(ies)."
        )
        for path in replay_dirs:
            print(f"  - {path}")
        print(f"Replay profiles: {[profile.name for profile in replay_profiles]}")
    else:
        print(
            f"Discovered {len(cases)} trajectory cases from "
            f"{len(trajectory_dirs)} directory(ies)."
        )
        for path in trajectory_dirs:
            print(f"  - {path}")
        if args.task_policy_map:
            print(
                f"Task policy map: {Path(args.task_policy_map).expanduser().resolve()}"
            )
        elif args.policy_file:
            print(
                f"Policy file (fallback for all tasks): "
                f"{Path(args.policy_file).expanduser().resolve()}"
            )
        else:
            built_in_domains = sorted({case.domain for case in cases})
            default_airline_policy = default_policy_path_for_domain("airline")
            policy_dir_text = (
                default_airline_policy.parent if default_airline_policy else "<unknown>"
            )
            print(f"Policy source: built-in defaults under {policy_dir_text}")
            print(f"Domains using built-in defaults: {built_in_domains}")

    if filtered_out:
        print(f"Filtered out {filtered_out} cases with spans > {args.max_spans}.")
    if balanced_selection_stats is not None:
        print(
            "Balanced expected-label sampling enabled: "
            f"selected {balanced_selection_stats['selected_total']} case(s) "
            f"(expected=0: {balanced_selection_stats['selected_zero']}, "
            f"expected=1: {balanced_selection_stats['selected_one']}) "
            f"from available "
            f"(expected=0: {balanced_selection_stats['available_zero']}, "
            f"expected=1: {balanced_selection_stats['available_one']})."
        )
        if balanced_selection_stats["available_other"] > 0:
            print(
                "Ignored case(s) with non-binary expected labels: "
                f"{balanced_selection_stats['available_other']}."
            )
        if (
            balanced_selection_stats["requested_total"]
            != balanced_selection_stats["requested_even_total"]
        ):
            print(
                "Adjusted requested eval count to keep an even split: "
                f"{balanced_selection_stats['requested_total']} -> "
                f"{balanced_selection_stats['requested_even_total']}."
            )
        if (
            balanced_selection_stats["selected_total"]
            < balanced_selection_stats["requested_even_total"]
        ):
            print("Balanced selection capped by minority label availability.")
    elif max_eval_filtered_out:
        print(f"Capped evaluation to first {len(cases)} case(s) via --max-evals.")

    lengths = _length_stats(cases)
    print(
        "Trace length stats: "
        f"count={lengths['count']} min={lengths['min']} max={lengths['max']} "
        f"mean={lengths['mean']:.2f} median={lengths['median']:.2f} "
        f"p90={lengths['p90']} p95={lengths['p95']}"
    )

    if args.lengths_only or args.show_lengths:
        _print_lengths(cases, limit=(0 if args.lengths_only else args.lengths_limit))

    if args.lengths_only:
        return

    if args.dry_run:
        print("Dry run enabled; skipping evaluation.")
        return

    report_path = (
        Path(args.report_json).expanduser().resolve()
        if args.report_json
        else _default_report_path()
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)

    # Replay mode supports profile-by-profile assumption testing from saved artifacts.
    if replay_mode:
        profile_reports: Dict[str, Dict[str, Any]] = {}
        profile_eval_outputs: Dict[str, Dict[str, Any]] = {}
        for profile in replay_profiles:
            eval_output = _evaluate_cases_via_replay(
                cases=cases,
                replay_artifacts=replay_artifacts,
                profile=profile,
            )
            report = _summarize(cases, eval_output)
            profile_reports[profile.name] = report
            profile_eval_outputs[profile.name] = eval_output
            print(
                f"\nReplay profile '{profile.name}': "
                f"acc={report['summary']['accuracy']:.4f} "
                f"matches={report['summary']['matches']} "
                f"mismatches={report['summary']['mismatches']}"
            )

        # When running multiple profiles, write a comparison artifact and skip
        # per-trajectory writes to avoid ambiguous output directories.
        if len(replay_profiles) > 1:
            comparison_rows = [
                {
                    "profile": profile.name,
                    "description": profile.description,
                    "accuracy": profile_reports[profile.name]["summary"]["accuracy"],
                    "matches": profile_reports[profile.name]["summary"]["matches"],
                    "mismatches": profile_reports[profile.name]["summary"][
                        "mismatches"
                    ],
                    "errors": profile_reports[profile.name]["summary"]["errors"],
                }
                for profile in replay_profiles
            ]
            comparison_rows.sort(key=lambda row: row["accuracy"], reverse=True)

            payload = {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "config": {
                    "mode": "replay",
                    "replay_per_trajectory_dirs": [str(path) for path in replay_dirs],
                    "replay_profiles": [profile.name for profile in replay_profiles],
                    "session_id_regex": args.session_id_regex,
                    "max_files": args.max_files,
                    "max_spans": args.max_spans,
                    "max_evals": args.max_evals,
                },
                "trace_length_stats": lengths,
                "comparison": comparison_rows,
                "profiles": {
                    profile.name: {
                        "profile": asdict(profile),
                        **profile_reports[profile.name],
                    }
                    for profile in replay_profiles
                },
            }
            with open(report_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            print("\nReplay profile comparison:")
            for row in comparison_rows:
                print(
                    f"  {row['profile']}: acc={row['accuracy']:.4f} "
                    f"match={row['matches']} mismatch={row['mismatches']} "
                    f"errors={row['errors']}"
                )
            print(f"\nReport JSON saved to: {report_path}")
            return

        # Single replay profile: keep existing summary + per-trajectory writer behavior.
        selected_profile = replay_profiles[0]
        eval_output = profile_eval_outputs[selected_profile.name]
        report = profile_reports[selected_profile.name]
        per_trajectory_dir: Optional[Path] = None
        per_trajectory_written = 0
        if not args.no_save_per_trajectory:
            per_trajectory_dir = (
                Path(args.per_trajectory_dir).expanduser().resolve()
                if args.per_trajectory_dir
                else _default_per_trajectory_dir(report_path)
            )
            per_trajectory_written = _write_per_trajectory_results(
                output_dir=per_trajectory_dir,
                cases=cases,
                eval_output=eval_output,
                report_rows=report["rows"],
            )

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "config": {
                "mode": "replay",
                "replay_profile": selected_profile.name,
                "replay_profile_config": asdict(selected_profile),
                "replay_per_trajectory_dirs": [str(path) for path in replay_dirs],
                "session_id_regex": args.session_id_regex,
                "max_files": args.max_files,
                "max_spans": args.max_spans,
                "max_evals": args.max_evals,
                "per_trajectory_dir": args.per_trajectory_dir,
                "no_save_per_trajectory": args.no_save_per_trajectory,
            },
            "per_trajectory_results": {
                "enabled": not args.no_save_per_trajectory,
                "output_dir": str(per_trajectory_dir) if per_trajectory_dir else None,
                "files_written": per_trajectory_written,
            },
            "trace_length_stats": lengths,
            **report,
        }
        with open(report_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

        _print_summary(payload["summary"], payload["rows"], verbose=args.verbose)
        print(f"\nReport JSON saved to: {report_path}")
        if per_trajectory_dir:
            print(
                f"Per-trajectory JSON saved to: {per_trajectory_dir} "
                f"(files={per_trajectory_written})"
            )
        return

    eval_output = _evaluate_cases(cases, args=args)
    report = _summarize(cases, eval_output)

    per_trajectory_dir: Optional[Path] = None
    per_trajectory_written = 0
    if not args.no_save_per_trajectory:
        per_trajectory_dir = (
            Path(args.per_trajectory_dir).expanduser().resolve()
            if args.per_trajectory_dir
            else _default_per_trajectory_dir(report_path)
        )
        per_trajectory_written = _write_per_trajectory_results(
            output_dir=per_trajectory_dir,
            cases=cases,
            eval_output=eval_output,
            report_rows=report["rows"],
        )

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "mode": "in-process",
            "temporal_evals_url": None,
            "trajectory_dirs": [str(path) for path in trajectory_dirs],
            "glob_pattern": args.glob_pattern,
            "max_files": args.max_files,
            "max_spans": args.max_spans,
            "max_evals": args.max_evals,
            "chunk_size": args.chunk_size,
            "batch_size": args.batch_size,
            "parallel_evals": args.parallel_evals,
            "fatality_threshold": args.fatality_threshold,
            "llm_model_name": args.llm_model_name,
            "session_id_regex": args.session_id_regex,
            "per_trajectory_dir": args.per_trajectory_dir,
            "no_save_per_trajectory": args.no_save_per_trajectory,
            "policy_file": args.policy_file,
            "task_policy_map": args.task_policy_map,
        },
        "per_trajectory_results": {
            "enabled": not args.no_save_per_trajectory,
            "output_dir": str(per_trajectory_dir) if per_trajectory_dir else None,
            "files_written": per_trajectory_written,
        },
        "trace_length_stats": lengths,
        **report,
    }

    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)

    _print_summary(payload["summary"], payload["rows"], verbose=args.verbose)
    print(f"\nReport JSON saved to: {report_path}")
    if per_trajectory_dir:
        print(
            f"Per-trajectory JSON saved to: {per_trajectory_dir} "
            f"(files={per_trajectory_written})"
        )


if __name__ == "__main__":
    main()
