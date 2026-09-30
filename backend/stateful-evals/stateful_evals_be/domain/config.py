#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Domain configuration and trajectory loading.

Handles domain-specific paths, trajectory file discovery,
system message loading, and tool definition loading.
Supports: airline, retail, telecom, noa domains.
"""

import glob
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from stateful_evals_be.policy_loader import default_policy_path_for_domain

# Base directory: stateful_evals/backend
BASE_DIR = Path(__file__).parent.parent.parent
LOCAL_TRAJECTORY_ROOT = BASE_DIR / "data" / "trajectories"

# Supported domains
SUPPORTED_DOMAINS = ["airline", "retail", "telecom", "noa"]


def get_domain_config(
    domain: str,
    trajectory_dir_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get domain-specific configuration paths and settings.

    Args:
        domain: The domain name (airline, retail, telecom, noa)
        trajectory_dir_override: Optional override for trajectory directory path

    Returns:
        Dict with trajectory_dir, tool_map_path, system_message_path, is_noa

    Raises:
        FileNotFoundError: If required paths don't exist
        ValueError: If domain is unsupported
    """
    if domain not in SUPPORTED_DOMAINS:
        raise ValueError(
            f"Unsupported domain '{domain}'. Supported: {SUPPORTED_DOMAINS}"
        )

    script_dir = BASE_DIR

    # Check for NOA domain
    use_noa = (
        domain == "noa" or os.environ.get("USE_NOA_TRAJECTORIES", "").lower() == "true"
    )
    noa_subdir = os.environ.get("NOA_SUBDIR", "gpt35_curated")

    if use_noa:
        return _get_noa_config(script_dir, noa_subdir, trajectory_dir_override)

    return _get_tau2_config(script_dir, domain, trajectory_dir_override)


def _get_noa_config(
    script_dir: Path,
    noa_subdir: str,
    trajectory_dir_override: Optional[str],
) -> Dict[str, Any]:
    """Build config for NOA Trip Planner domain."""
    candidates: List[Path] = []
    if trajectory_dir_override:
        trajectory_dir = Path(trajectory_dir_override)
        candidates = [trajectory_dir]
    else:
        if noa_subdir:
            candidates.append(LOCAL_TRAJECTORY_ROOT / "noa_trip_planner" / noa_subdir)
        candidates.append(LOCAL_TRAJECTORY_ROOT / "noa_trajectories")
        candidates.append(LOCAL_TRAJECTORY_ROOT / "noa_trip_planner")

        trajectory_dir = None
        for candidate in candidates:
            if candidate.exists():
                trajectory_dir = candidate
                break

    if trajectory_dir is None or not trajectory_dir.exists():
        raise FileNotFoundError(
            f"NOA trajectory directory not found: {trajectory_dir}. "
            f"Looked in: {[str(c) for c in candidates]}. "
            f"Set NOA_SUBDIR env var, pass --trajectory-dir, or add local data."
        )

    tool_map_path = script_dir / "noa_tool_map.json"
    if not tool_map_path.exists():
        raise FileNotFoundError(
            f"Tool map not found: {tool_map_path}. Run: python noa_tool_extractor.py"
        )

    system_message_path = default_policy_path_for_domain("noa")
    if system_message_path is None or not system_message_path.exists():
        # Backward-compatible fallback
        fallback = script_dir / "noa_policy.md"
        if fallback.exists():
            system_message_path = fallback
        else:
            print(f"Warning: NOA policy file not found at {fallback}")
            system_message_path = None

    return {
        "domain": "noa",
        "trajectory_dir": trajectory_dir,
        "tool_map_path": tool_map_path,
        "system_message_path": system_message_path,
        "is_noa": True,
    }


def _get_tau2_config(
    script_dir: Path,
    domain: str,
    trajectory_dir_override: Optional[str],
) -> Dict[str, Any]:
    """Build config for TAU-2 benchmark domains (airline, retail, telecom)."""
    if trajectory_dir_override:
        trajectory_dir = Path(trajectory_dir_override)
    else:
        # Search for trajectory directory
        if domain == "airline":
            candidates = [
                LOCAL_TRAJECTORY_ROOT / "tau2_trajectories",
                LOCAL_TRAJECTORY_ROOT / "tau2_trajectories_airline",
            ]
        else:
            candidates = [
                LOCAL_TRAJECTORY_ROOT / f"tau2_trajectories_{domain}",
                LOCAL_TRAJECTORY_ROOT / "tau2_trajectories",
            ]

        trajectory_dir = None
        for candidate in candidates:
            if candidate.exists():
                trajectory_dir = candidate
                break

        if trajectory_dir is None:
            raise FileNotFoundError(
                f"No trajectory directory found for domain '{domain}'. "
                f"Looked for: {[str(c) for c in candidates]}"
            )

    # Tool map
    tool_map_path = script_dir / f"{domain}_tool_map.json"
    if not tool_map_path.exists():
        raise FileNotFoundError(
            f"Tool map not found: {tool_map_path}. Run: python tool_extractor.py {domain}"
        )

    # System message: prefer local copied policy files under stateful_evals_be/policies.
    system_message_path = default_policy_path_for_domain(domain)
    if system_message_path is None or not system_message_path.exists():
        # Backward-compatible fallback to tau2-bench result JSON extraction path.
        tau2_bench_results = (
            script_dir / "tau2-bench" / "data" / "tau2" / "results" / "final"
        )
        system_message_candidates = list(
            tau2_bench_results.glob(f"*_{domain}_default_*.json")
        )
        system_message_path = (
            system_message_candidates[0] if system_message_candidates else None
        )

    return {
        "domain": domain,
        "trajectory_dir": trajectory_dir,
        "tool_map_path": tool_map_path,
        "system_message_path": system_message_path,
        "is_noa": False,
    }


def load_trajectories(
    trajectory_dir: Path,
    max_spans: int = 18,
    is_noa: bool = False,
) -> Tuple[List[str], List[str]]:
    """
    Load and categorize trajectories from a directory.

    Args:
        trajectory_dir: Path to trajectory directory
        max_spans: Maximum number of spans to include (filter out long trajectories)
        is_noa: If True, handle NOA format (train/test subdirs, different reward location)

    Returns:
        Tuple of (correct_trajectories, incorrect_trajectories) file paths
    """
    correct_trajectories: List[str] = []
    incorrect_trajectories: List[str] = []

    # Determine file patterns based on directory structure
    if is_noa:
        train_dir = trajectory_dir / "train"
        test_dir = trajectory_dir / "test"

        if train_dir.exists() and test_dir.exists():
            file_patterns = [
                str(train_dir / "*.json"),
                str(test_dir / "*.json"),
            ]
        else:
            file_patterns = [str(trajectory_dir / "*.json")]
    else:
        file_patterns = [str(trajectory_dir / "*.json")]

    for pattern in file_patterns:
        for file_path in glob.glob(pattern):
            try:
                with open(file_path, "rb") as f:
                    data = json.load(f)

                # Handle both NOA format (top-level reward) and tau2 format
                reward = data.get("reward")
                if reward is None:
                    reward = data.get("reward_info", {}).get("reward")

                num_spans = len(data.get("spans", []))

                if reward == 1 or reward == 1.0:
                    if num_spans < max_spans:
                        correct_trajectories.append(file_path)
                elif reward == 0 or reward == 0.0:
                    if num_spans < max_spans:
                        incorrect_trajectories.append(file_path)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

    return correct_trajectories, incorrect_trajectories


def load_system_message(system_message_path: Optional[Path]) -> str:
    """Load the system message/policy from a file.

    Supports:
    - .md files: Read directly as text
    - .json files: Extract from nested structure (tau2-bench format)
    """
    if system_message_path is None or not Path(system_message_path).exists():
        print("Warning: No system message file found. Using empty policy.")
        return ""

    system_message_path = Path(system_message_path)

    if system_message_path.suffix == ".md":
        with open(system_message_path, "r", encoding="utf-8") as f:
            return f.read()

    with open(system_message_path, "rb") as f:
        data = json.load(f)

    return data.get("info", {}).get("environment_info", {}).get("policy", "")


def load_tool_definitions(tool_map_path: Path) -> Dict[str, Any]:
    """Load tool definitions from a tool map JSON file."""
    with open(tool_map_path, "rb") as f:
        return json.load(f)
