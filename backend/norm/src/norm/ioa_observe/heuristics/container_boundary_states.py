#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Give MASCall and Session their own initial/final State by sharing (not
bridging) with the first/last child that actually starts/ends them.

Runs last, after chain_capability_calls, since it needs every AgentCall's
own boundary State edges in their final, possibly-bridged form. MASCall is
resolved before Session so that Session's own adoption can build on
MASCall's already-adopted boundary.
"""

from __future__ import annotations

from oxp_ontology.models.edges import (
    hasAgentCall,
    hasFinalState,
    hasInitialState,
    hasMASCall,
)
from oxp_ontology.models.nodes import AgentCall, MASCall, Session

from ..registry import Registry
from ..trajectory import adopt_boundary_states


def assign_container_boundary_states(registry: Registry) -> None:
    for mas_call in registry.all_of(MASCall):
        children = [
            registry.get(AgentCall, target_id)
            for target_id in registry.edges_from(hasAgentCall, mas_call.id)
        ]
        ordered = sorted((c for c in children if c is not None), key=lambda c: c.startTime)
        if not ordered:
            continue
        initial_state_id = registry.edge_target(hasInitialState, ordered[0].id)
        final_state_id = registry.edge_target(hasFinalState, ordered[-1].id)
        if initial_state_id is None or final_state_id is None:
            continue
        adopt_boundary_states(
            registry, mas_call.id, mas_call.sessionId, initial_state_id, final_state_id
        )

    for session in registry.all_of(Session):
        children = [
            registry.get(MASCall, target_id)
            for target_id in registry.edges_from(hasMASCall, session.id)
        ]
        ordered = sorted((c for c in children if c is not None), key=lambda c: c.startTime)
        if not ordered:
            continue
        initial_state_id = registry.edge_target(hasInitialState, ordered[0].id)
        final_state_id = registry.edge_target(hasFinalState, ordered[-1].id)
        if initial_state_id is None or final_state_id is None:
            continue
        adopt_boundary_states(
            registry, session.id, session.sessionId, initial_state_id, final_state_id
        )
