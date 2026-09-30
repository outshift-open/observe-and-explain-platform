#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Best-effort, timestamp-ordered chaining of capability calls (LLMCall/
ToolCall) within one AgentCall.

No SDK signal exists today for the real execution order of sibling
capability calls within a single agent invocation -- checked and ruled out:
SpanId isn't time-ordered (standard random OTel ids, confirmed by sorting
known-chronological examples and finding they don't match), ParentSpanId
nesting only groups siblings (every round of a tool-calling loop shares the
same immediate container span, so it can't tell rounds apart), and
gen_ai.task.parent.id groups at the whole-agent-invocation granularity, not
per-round. So this falls back to sorting by startTime, which is safe here
specifically because sibling capability calls within one agent invocation
are a strict request/response loop and don't overlap the way a task-wrapper
span overlaps the work nested inside it.

Also bridges the AgentCall's own boundary against the chain: the AgentCall's
own initial State against the first capability call's own initial State,
and the last capability call's own final State against the AgentCall's own
final State -- same bridge-if-mismatched rule as the interior sibling links,
not a replacement of either side's State.

Deliberately best-effort and skip-based (bridge_states_if_mismatched is a
no-op once a pair is already bridged): if the SDK later exports a real
per-call sequence and a dedicated resolver runs first, this only fills in
whatever that resolver left unresolved.
"""

from __future__ import annotations

from oxp_ontology.models.edges import hasFinalState, hasInitialState, hasLLMCall, hasToolCall
from oxp_ontology.models.nodes import AgentCall, LLMCall, ToolCall

from ..registry import Registry
from ..trajectory import bridge_states_if_mismatched


def chain_capability_calls(registry: Registry) -> None:
    for agent_call in registry.all_of(AgentCall):
        children = [
            *(
                registry.get(LLMCall, target_id)
                for target_id in registry.edges_from(hasLLMCall, agent_call.id)
            ),
            *(
                registry.get(ToolCall, target_id)
                for target_id in registry.edges_from(hasToolCall, agent_call.id)
            ),
        ]
        ordered = sorted(
            (child for child in children if child is not None), key=lambda c: c.startTime
        )
        if not ordered:
            continue

        first, last = ordered[0], ordered[-1]
        bridge_states_if_mismatched(
            registry,
            from_state_id=registry.edge_target(hasInitialState, agent_call.id),
            to_state_id=registry.edge_target(hasInitialState, first.id),
            attach_to_id=agent_call.id,
            session_id=agent_call.sessionId,
            start_time=agent_call.startTime,
            end_time=first.startTime,
            bridge_kind="capability-chain-boundary",
        )
        bridge_states_if_mismatched(
            registry,
            from_state_id=registry.edge_target(hasFinalState, last.id),
            to_state_id=registry.edge_target(hasFinalState, agent_call.id),
            attach_to_id=agent_call.id,
            session_id=agent_call.sessionId,
            start_time=last.endTime,
            end_time=agent_call.endTime,
            bridge_kind="capability-chain-boundary",
        )

        for previous, current in zip(ordered, ordered[1:]):
            bridge_states_if_mismatched(
                registry,
                from_state_id=registry.edge_target(hasFinalState, previous.id),
                to_state_id=registry.edge_target(hasInitialState, current.id),
                attach_to_id=agent_call.id,
                session_id=current.sessionId,
                start_time=previous.endTime,
                end_time=current.startTime,
                bridge_kind="capability-chain",
            )
