#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Dictionary-compatible contract for a normalized trajectory.

A trajectory is a session's LLM, tool and agent calls in execution order, each
with the raw text of its input and output. The caller (for example the
stateful-eval worker, which reads it from the knowledge graph) supplies it; this
library neither knows nor cares where it came from.
"""

from collections.abc import Mapping
from typing import Any, TypeAlias, TypedDict


class TrajectoryStep(TypedDict, total=False):
    transition_id: str  # identifies the step; echoed back on its metric results
    call_id: str  # id of the call itself
    kind: str  # "llm" | "tool" | "agent"
    name: str  # model, tool or agent name
    description: str  # tool steps: what the tool does
    agent_id: str  # the acting agent ("" when unknown)
    parent_id: str  # id of the agent call that owns an llm/tool call
    success: bool
    start_time: float  # epoch seconds
    duration_ms: float
    input_text: str  # raw State text going in
    output_text: str  # raw State text coming out


class TrajectoryRecord(TypedDict, total=False):
    session_id: str
    steps: list[TrajectoryStep]  # execution order


Trajectory: TypeAlias = TrajectoryRecord | Mapping[str, Any]
