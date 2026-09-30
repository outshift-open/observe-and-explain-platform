#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Link sequential AgentCalls across a handoff (moderator -> specialist -> moderator, ...).

Runs once, after every per-span handler, since it needs every AgentCall (and
its own initial/final State) to already exist.

Each "*.agent" span's ``ioa_observe.handoff.source.span_ids`` names the
predecessor span(s) directly -- a real edge, not a derived total order, so a
merge (multiple predecessors handed off into one successor) or a fork (one
predecessor, multiple successors) both fall out of just handling each
(predecessor, successor) pair independently; no separate case for either.

Rule of thumb: if the predecessor's own final-state content is literally the
successor's own initial-state content, they're already continuous and
nothing more is asserted. Otherwise, bridge the gap with a synthesized
ProcessingCall (attached to the successor's MASCall) whose own initial/final
states *reuse* the two existing States, rather than asserting a false direct
link between them.

When a span carries no ``ioa_observe.handoff.source.span_ids`` signal at
all, ``chain_agent_handoffs_fallback`` (run after this) falls back to
timestamp order, same rationale as
``capability_chain.chain_capability_calls``: sibling AgentCalls under one
MASCall are still a strict sequential handoff chain (moderator ->
specialist -> moderator, ...) absent a real per-call signal, so sorting by
startTime is safe. It never overrides an AgentCall that did have an
explicit signal, even a signal that didn't resolve to a real predecessor
-- an explicit (if incomplete) signal always wins over a guess.
"""

from __future__ import annotations

import json
from typing import Any

from oxp_ontology.models.edges import hasAgentCall, hasFinalState, hasInitialState
from oxp_ontology.models.nodes import AgentCall, MASCall

from ..fields import _hash_id, attrs, get_agent_id
from ..registry import Registry
from ..trajectory import bridge_states_if_mismatched


def _source_span_ids(span_attrs: dict[str, Any]) -> list[str]:
    raw = span_attrs.get("ioa_observe.handoff.source.span_ids")
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _bridge_if_needed(
    registry: Registry,
    source_call: AgentCall,
    target_call: AgentCall,
    bridge_kind: str = "handoff",
) -> None:
    mas_call_id = registry.edge_source(hasAgentCall, target_call.id)
    if mas_call_id is None:
        return  # no MASCall to attach the bridge to
    bridge_states_if_mismatched(
        registry,
        from_state_id=registry.edge_target(hasFinalState, source_call.id),
        to_state_id=registry.edge_target(hasInitialState, target_call.id),
        attach_to_id=mas_call_id,
        session_id=target_call.sessionId,
        start_time=source_call.endTime,
        end_time=target_call.startTime,
        bridge_kind=bridge_kind,
    )


def link_agent_handoffs(spans: list[dict[str, Any]], registry: Registry) -> set[str]:
    """Bridge every explicitly-signalled (predecessor, successor) pair.

    Returns the set of successor AgentCall ids that carried a
    ``ioa_observe.handoff.source.span_ids`` signal, whether or not it
    resolved to a real predecessor -- ``chain_agent_handoffs_fallback``
    uses this to know which AgentCalls to leave alone.
    """
    explicit_targets: set[str] = set()
    for span in spans:
        span_name = str(span.get("SpanName") or "")
        if not span_name.endswith(".agent"):
            continue
        span_attrs = attrs(span)
        source_span_ids = _source_span_ids(span_attrs)
        if not source_span_ids:
            continue

        agent_id = get_agent_id(span, span_attrs)
        span_id = str(span.get("SpanId") or "")
        target_call = registry.get(AgentCall, _hash_id("agentcall", agent_id, span_id))
        if target_call is None:
            continue

        explicit_targets.add(target_call.id)
        for source_span_id in source_span_ids:
            source_call = registry.find(AgentCall, lambda a, sid=source_span_id: a.spanId == sid)
            if source_call is not None:
                _bridge_if_needed(registry, source_call, target_call)

    return explicit_targets


def chain_agent_handoffs_fallback(registry: Registry, explicit_targets: set[str]) -> None:
    """Best-effort, timestamp-ordered chaining of sibling AgentCalls within
    one MASCall, for whichever AgentCalls ``link_agent_handoffs`` left
    untouched (no handoff signal at all).

    Mirrors ``capability_chain.chain_capability_calls``'s fallback: sort
    siblings by startTime and bridge each consecutive pair. Only the
    successor side of a pair needs to be signal-free to skip it here --
    if it already got an explicit (if unresolved) signal, an explicit
    source is trusted over a guessed one even when that guess would have
    picked the same predecessor.

    Unlike capability calls (a guaranteed non-overlapping request/response
    loop), every AgentCall in a MAS attaches directly to the same MASCall
    regardless of real nesting -- a sub-agent invoked synchronously inside
    its caller's own span still lands here as a flat sibling. Such a call's
    ``parentSpanId`` points at another AgentCall's own ``spanId`` rather
    than some span outside this set, which is how it's told apart and
    excluded: it's contained within its parent's execution window, not a
    predecessor/successor peer, and chaining it in by timestamp would
    assert a false handoff into and out of a span that's still part of its
    parent's own call.
    """
    for mas_call in registry.all_of(MASCall):
        children = [
            registry.get(AgentCall, target_id)
            for target_id in registry.edges_from(hasAgentCall, mas_call.id)
        ]
        children = [child for child in children if child is not None]
        sibling_span_ids = {child.spanId for child in children}
        top_level = [child for child in children if child.parentSpanId not in sibling_span_ids]
        ordered = sorted(top_level, key=lambda a: a.startTime)
        for previous, current in zip(ordered, ordered[1:]):
            if current.id in explicit_targets:
                continue
            _bridge_if_needed(registry, previous, current, bridge_kind="handoff-fallback")
