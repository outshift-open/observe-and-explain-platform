#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

"""Shared helpers for metric-side error and completion inference.

``contains_error`` is the one signal the provider layer derives from a call
node's ``success`` field (``contains_error = success is False``; no signal
recorded is not a failure) -- see ``OXPKGProvider._normalize_tool_call``/
``_normalize_llm_call``. There is no raw ``status``/``error`` KG field to read
instead; ``success`` is the only execution-outcome signal the ontology
carries.
"""


def is_execution_error(call: Any) -> bool:
    if isinstance(call, dict):
        return bool(call.get("contains_error"))
    return bool(getattr(call, "contains_error", False))


def count_execution_errors(calls: list[Any]) -> int:
    return sum(1 for call in calls if is_execution_error(call))


def derive_session_completion(llm_calls: list[Any], tool_calls: list[Any]) -> bool:
    """Infer session completion from raw child call outcomes.

    A session is considered completed when each present child-call category has
    at least one non-failing execution.
    """
    llm_total = len(llm_calls)
    llm_failed = count_execution_errors(llm_calls)
    tool_total = len(tool_calls)
    tool_failed = count_execution_errors(tool_calls)

    llm_completed = llm_total == 0 or llm_failed < llm_total
    tool_completed = tool_total == 0 or tool_failed < tool_total
    return llm_completed and tool_completed
