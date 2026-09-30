#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import re
from typing import Any

"""Metric-local workaround helpers for legacy workflow payload anomalies.

Convention
----------
This module only repairs already-fetched context for workflow metrics. It must
not perform its own KG lookup. If a fallback requires a second ontology-versus-
legacy Neo4j query, that fallback belongs at the oxp-api provider boundary.
"""


def collapse_duplicate_agent_calls(
    agent_calls: list[Any], agent_name_getter
) -> list[Any]:
    """WORKAROUND: compact legacy KG task/call duplicates.

    Some Neo4j datasets contain two consecutive ``:AgentCall`` nodes for the
    same logical handoff, typically one ``*_task_*`` node and one ``*_call_*``
    node. In the affected data these duplicates share the same ``spanId`` and
    agent identity, but they would otherwise appear as two separate workflow
    steps.

    This compatibility shim keeps one representative node for each consecutive
    duplicate pair so workflow metrics can operate on the logical sequence.
    """
    collapsed: list[Any] = []
    previous_name: str | None = None
    previous_signature: str | None = None

    for agent_call in agent_calls:
        name = agent_name_getter(agent_call)
        signature = _agent_call_signature(agent_call)

        if (
            collapsed
            and name is not None
            and signature is not None
            and name == previous_name
            and signature == previous_signature
        ):
            continue

        collapsed.append(agent_call)
        previous_name = name
        previous_signature = signature

    return collapsed


def _agent_call_attr(agent_call: Any, *names: str) -> Any:
    if isinstance(agent_call, dict):
        for name in names:
            value = agent_call.get(name)
            if value is not None:
                return value
        return None
    for name in names:
        value = getattr(agent_call, name, None)
        if value is not None:
            return value
    return None


def _agent_call_signature(agent_call: Any) -> str | None:
    span_id = _agent_call_attr(agent_call, "spanId", "span_id", "agent_span_id")
    if span_id:
        return f"span:{span_id}"

    execution_id = _agent_call_attr(agent_call, "executionId", "execution_id")
    if execution_id:
        canonical = re.sub(r"_(task|call)_", "_", str(execution_id))
        return f"exec:{canonical}"

    return None
