#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""The cognitive failures the worker can look for, from the challenges taxonomy."""

from __future__ import annotations

import json
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).resolve().parent / "data" / "failures.json"


@lru_cache(maxsize=1)
def all_failures() -> dict[str, dict[str, Any]]:
    """Every failure of the taxonomy by code (regenerate with scripts/build_failures.py)."""
    return {c["code"]: c for c in json.loads(_DATA.read_text(encoding="utf-8"))["failures"]}


def select_failures(codes: Iterable[str]) -> list[dict[str, Any]]:
    """The failures with these codes, in the given order. Raises ``ValueError`` on an unknown code.

    Codes are matched ignoring case, so ``ic-2`` is ``IC-2``.
    """
    known = all_failures()
    selected: dict[str, dict[str, Any]] = {}
    unknown = []
    for code in codes:
        failure = known.get(str(code).strip().upper())
        if failure is None:
            unknown.append(str(code))
        else:
            selected[failure["code"]] = failure
    if unknown:
        raise ValueError(f"Unknown cognitive failure(s): {', '.join(unknown)}. Available: {', '.join(known)}")
    return list(selected.values())
