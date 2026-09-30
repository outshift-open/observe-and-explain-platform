#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from collections import Counter
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics.workflow.workflow_efficiency_workaround import (
    collapse_duplicate_agent_calls,
)


def _agent_name(agent_call: Any) -> str | None:
    if isinstance(agent_call, dict):
        return (
            agent_call.get("agentName")
            or agent_call.get("name")
            or agent_call.get("agent_id")
            or agent_call.get("id")
            or agent_call.get("executionId")
        )
    return (
        getattr(agent_call, "agentName", None)
        or getattr(agent_call, "name", None)
        or getattr(agent_call, "agent_id", None)
        or getattr(agent_call, "id", None)
        or getattr(agent_call, "executionId", None)
    )


def _derive_transitions(agent_calls: list[Any]) -> list[str]:
    names = [
        name for name in (_agent_name(agent_call) for agent_call in agent_calls) if name
    ]
    return [f"{left}->{right}" for left, right in zip(names, names[1:])]


def _agent_chain(agent_calls: list[Any]) -> list[str]:
    return [
        name for name in (_agent_name(agent_call) for agent_call in agent_calls) if name
    ]


class WorkflowEfficiency(Metric):
    """Measures workflow efficiency from the ordered AgentCall sequence.

    Includes a temporary legacy-KG workaround that collapses duplicated
    ``*_task_*`` / ``*_call_*`` AgentCall pairs before deriving the logical
    agent chain.
    """

    metadata = SpecRegistry.require("WorkflowEfficiency").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return SpecRegistry.require("WorkflowEfficiency").input_requirements

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        agent_calls = context.get("agent_calls", [])
        session = context.get("session")
        if session:
            agent_calls = getattr(session, "agent_calls", agent_calls)

        # WORKAROUND: neutralize duplicated task/call AgentCall pairs coming
        # from legacy ingestion so this metric reflects logical handoffs.
        agent_calls = collapse_duplicate_agent_calls(agent_calls, _agent_name)

        chain = _agent_chain(agent_calls)
        transitions = [f"{left}->{right}" for left, right in zip(chain, chain[1:])]
        counts = Counter(transitions)

        total_transitions = len(transitions)
        unique_transitions = len(counts)
        efficiency_score = 0.0
        if total_transitions:
            efficiency_score = min(1.0, unique_transitions / total_transitions)

        if chain:
            reasoning = (
                f"Agent chain: {' -> '.join(chain)} | "
                f"unique_transitions={unique_transitions} total_transitions={total_transitions}"
            )
        else:
            reasoning = "No agent call sequence available for this session."

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=efficiency_score,
            metric_class=self.ontology_class,
            reasoning=reasoning,
            metadata={
                "total_transitions": total_transitions,
                "unique_transitions": unique_transitions,
                "agent_chain": chain,
            },
        )
