#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Policy loading utilities for stateful_evals_be.

Provides:
- built-in policy defaults for currently supported domains
- optional task-level policy map loading
- strict fallback behavior for unknown future domains
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

POLICY_DIR = Path(__file__).resolve().parent / "policies"

# Current built-in policy files copied into stateful_evals_be/policies.
KNOWN_DOMAIN_POLICY_FILES = {
    "airline": "tau2_airline.md",
    "retail": "tau2_retail.md",
    "telecom": "tau2_telecom.md",
    "noa": "noa.md",
}


def _read_policy_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Policy file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Policy file is empty: {path}")
    return text


def default_policy_path_for_domain(domain: str) -> Optional[Path]:
    file_name = KNOWN_DOMAIN_POLICY_FILES.get((domain or "").strip().lower())
    if not file_name:
        return None
    return POLICY_DIR / file_name


def resolve_policy_text(
    *,
    domain: str,
    policy_file: Optional[str] = None,
    policy_text: Optional[str] = None,
) -> str:
    """Resolve policy text for a domain.

    Resolution order:
    1) explicit policy_text
    2) explicit policy_file
    3) built-in domain policy file (if available)

    For unknown domains, raises ValueError unless explicit policy was provided.
    """
    if policy_text and policy_text.strip():
        return policy_text.strip()

    if policy_file and policy_file.strip():
        return _read_policy_file(Path(policy_file).expanduser().resolve())

    built_in_path = default_policy_path_for_domain(domain)
    if built_in_path and built_in_path.exists():
        return _read_policy_file(built_in_path)

    raise ValueError(
        f"No built-in policy for domain '{domain}'. "
        "Please provide a policy via --policy-file, --task-policy-map, or API policy fields."
    )


def _resolve_map_entry_to_policy_text(
    entry: Any,
    *,
    map_dir: Path,
) -> str:
    """Resolve a single policy-map entry to policy text.

    Supported values:
    - string:
      - interpreted as a file path (absolute or relative to map file dir)
      - if not found, interpreted as a file under POLICY_DIR
      - if still not found, treated as raw policy text
    - object:
      - {"policy_file": "..."} or {"policy_text": "..."}
    """
    if isinstance(entry, str):
        candidate_paths = [
            Path(entry).expanduser(),
            map_dir / entry,
            POLICY_DIR / entry,
        ]
        for candidate in candidate_paths:
            resolved = candidate.resolve()
            if resolved.exists() and resolved.is_file():
                return _read_policy_file(resolved)
        if entry.strip():
            return entry.strip()
        raise ValueError("Policy map entry is an empty string.")

    if isinstance(entry, dict):
        raw_text = entry.get("policy_text")
        if isinstance(raw_text, str) and raw_text.strip():
            return raw_text.strip()

        raw_file = entry.get("policy_file")
        if isinstance(raw_file, str) and raw_file.strip():
            file_path = Path(raw_file).expanduser()
            candidate_paths = [file_path, map_dir / file_path, POLICY_DIR / file_path]
            for candidate in candidate_paths:
                resolved = candidate.resolve()
                if resolved.exists() and resolved.is_file():
                    return _read_policy_file(resolved)
            raise FileNotFoundError(f"Policy file from map entry not found: {raw_file}")

        raise ValueError(
            "Policy map object entries must contain non-empty 'policy_text' or 'policy_file'."
        )

    raise ValueError(
        "Unsupported policy map entry type. Use string or object with policy_text/policy_file."
    )


def load_task_policy_text_map(policy_map_file: Optional[str]) -> Dict[str, str]:
    """Load task->policy_text mapping from JSON file.

    Returns empty dict when no map file is provided.
    """
    if not policy_map_file:
        return {}

    map_path = Path(policy_map_file).expanduser().resolve()
    if not map_path.exists() or not map_path.is_file():
        raise FileNotFoundError(f"Task policy map file not found: {map_path}")

    raw = json.loads(map_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Task policy map must be a JSON object.")

    map_dir = map_path.parent
    resolved: Dict[str, str] = {}
    for raw_key, entry in raw.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError("Task policy map contains an empty key.")
        resolved[key] = _resolve_map_entry_to_policy_text(entry, map_dir=map_dir)
    return resolved
