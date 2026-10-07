#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Trajectory Context: stateful accumulator for evaluation context.

Tracks four categories of information as spans are processed sequentially:

1. **Evidence** (for Groundedness): tool outputs, user statements, policy rules.
   Tool outputs are authoritative — they are ground truth.  Agent outputs are
   deliberately excluded as evidence (they are what we evaluate).

2. **Intents** (for Intent Recognition): work items that agents assign to
   one another, linked to spans by explicit references and recorded ids.
   Completion is left to the judges.

3. **Claims** (for Relevancy): agent assertions, decisions, state
   transitions.  Provides the "reasoning history" that relevancy is checked
   against.

4. **Coordination**: topology-independent work ownership, handoffs, peer
   context, revisions, verification, selection, synthesis, and commit events.
   Typed provenance links retain which prior artifacts and spans informed each
   transition.

Each metric receives a tailored context string assembled from the relevant
category, keeping prompts focused and token-efficient.
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from stateful_evals_be.evaluation.coordination import CoordinationContext

logger = logging.getLogger("stateful_evals_be.trajectory_context")

@dataclass
class EvidenceFact:
    """A single piece of evidence extracted from the trajectory."""

    span_index: int
    # policy_rule | tool_output | user_statement | agent_handoff |
    # environment_context | runtime_feedback
    fact_type: str
    content: str
    source_name: str
    agent_id: str = ""
    actor_scope: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    trace_id: str = ""
    related_intent_ids: List[str] = field(default_factory=list)
    # Work unit this fact was produced under (``work:N``), if any.
    work_id: str = ""
    # Tool facts only: ``output`` | ``error`` | ``no_output``.
    outcome: str = ""
    # Set when an allocator's delegation tool relays another agent's reply.
    relayed_from_agent_id: str = ""
    # Tool facts only: the span's start (epoch ns) and OTel ``Duration`` (ns).
    started_at_ns: Optional[int] = None
    duration_ns: Optional[int] = None


@dataclass
class IntentEntry:
    """A tracked intent (user request or system constraint)."""

    name: str
    source: str  # "user" | "policy" | "agent_plan"
    first_seen: int  # span index
    last_seen: int
    # "in_progress" for an assigned work item; other values are read back from
    # persisted artifacts ("pending" | "fulfilled" | "dropped").
    status: str
    description: str = ""
    requirement_type: str = "request"
    events: List[Dict[str, Any]] = field(default_factory=list)
    owner_agent_ids: List[str] = field(default_factory=list)
    assigned_by_agent_id: str = ""
    assignment_mode: str = ""
    parent_intent_ids: List[str] = field(default_factory=list)
    dependency_intent_ids: List[str] = field(default_factory=list)
    expected_output: str = ""
    phase: str = ""
    round_index: Optional[int] = None


@dataclass
class ClaimEntry:
    """An agent claim or decision recorded for consistency checking."""

    span_index: int
    claim_type: (
        str  # "assertion" | "peer_agent_assertion" | "completion_claim" | "tool_result"
    )
    content: str
    entity_name: str
    agent_id: str = ""
    actor_scope: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    trace_id: str = ""
    related_intent_ids: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    revision_of_claim_id: str = ""
    phase: str = ""
    round_index: Optional[int] = None
    work_id: str = ""
    # Tool results only: ``output`` | ``error`` | ``no_output``.
    outcome: str = ""
    relayed_from_agent_id: str = ""


@dataclass
class CoordinationEvent:
    """A topology-independent coordination transition observed in the trace."""

    event_id: str
    span_index: int
    event_type: str
    operation_name: str
    actor_agent_id: str = ""
    sender_agent_ids: List[str] = field(default_factory=list)
    recipient_agent_ids: List[str] = field(default_factory=list)
    related_intent_ids: List[str] = field(default_factory=list)
    input_artifact_ids: List[str] = field(default_factory=list)
    output_artifact_ids: List[str] = field(default_factory=list)
    linked_span_ids: List[str] = field(default_factory=list)
    link_types: List[str] = field(default_factory=list)
    assignment_mode: str = ""
    status: str = ""
    content: str = ""
    phase: str = ""
    round_index: Optional[int] = None
    span_id: str = ""
    parent_span_id: str = ""
    trace_id: str = ""
    work_id: str = ""
    # Outcome of the delegation this event carries; see ``WorkUnit.outcome``.
    # Unlike ``status`` it is never overwritten by a later span merge.
    outcome: str = ""
    # Adapter-native event index (e.g. an events.jsonl line), kept separate
    # from ``span_index`` so the two index spaces are never compared.
    source_event_index: Optional[int] = None


@dataclass
class AgentProfile:
    """What the trajectory declares and shows about one agent."""

    agent_id: str
    first_seen: int = -1
    last_seen: int = -1
    # How the agent became known: trace_scan | adapter_edge | observed |
    # capability_table.
    declared_by: List[str] = field(default_factory=list)
    span_count: int = 0
    llm_span_count: int = 0
    tool_span_count: int = 0
    # semantic_contract / policy artifact ids that carry its instructions.
    contract_ids: List[str] = field(default_factory=list)
    # Capability line an allocator's roster table declares for this agent.
    declared_capability: str = ""
    declared_capability_source: str = ""
    # Tools bound to its LLM calls vs tools it actually executed.
    declared_tools: List[str] = field(default_factory=list)
    observed_tools: List[str] = field(default_factory=list)
    allocated_work_ids: List[str] = field(default_factory=list)
    received_work_ids: List[str] = field(default_factory=list)
    # False for framework components that carry an agent attribute but never
    # made an LLM call or ran a tool (for example a finalize node).
    active: bool = True


@dataclass
class WorkUnit:
    """One allocation of work from an allocator to a recipient.

    ``outcome`` values:

    * ``pending`` - assigned, not yet resolved;
    * ``completed`` - the recipient returned a substantive reply;
    * ``failed`` - the delegation or the recipient errored;
    * ``needs_input`` - the recipient asked for missing information;
    * ``waiting`` - the recipient said it is waiting on another party;
    * ``declined`` - the recipient said it cannot or will not do the work;
    * ``unfinished`` - received but not resolved by the delivery boundary;
    * ``no_response`` - never received, or no reply by the boundary.
    """

    work_id: str
    allocator_agent_id: str
    recipient_agent_ids: List[str] = field(default_factory=list)
    request: str = ""
    request_span_index: int = -1
    # span (delegation tool/operation) | adapter (coordination sidecar edge) |
    # route (framework router output) | message (typed message target)
    source: str = "span"
    call_id: str = ""
    edge_id: str = ""
    source_event_index: Optional[int] = None
    source_span_ids: List[str] = field(default_factory=list)
    assignment_event_ids: List[str] = field(default_factory=list)
    intent_id: str = ""
    # Loop span indexes where a recipient executed under this unit.
    receipt_span_indices: List[int] = field(default_factory=list)
    response_span_index: int = -1
    response_artifact_ids: List[str] = field(default_factory=list)
    outcome: str = "pending"
    outcome_basis: str = ""
    outcome_span_index: int = -1
    attempt_index: int = 1
    retry_of_work_id: str = ""
    # same_request (the text matches) | same_recipients (the allocator went
    # back to the same recipients after an unresolved attempt).
    retry_basis: str = ""
    previous_owner_agent_ids: List[str] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FlagEntry:
    """An agent's own statement that work is blocked, missing, or not its job."""

    flag_id: str
    span_index: int
    agent_id: str
    # needs_input | waiting | cannot_do | out_of_scope
    kind: str
    quote: str
    artifact_id: str = ""
    work_id: str = ""


@dataclass
class ArtifactProvenanceLink:
    """A typed relationship between two persisted trajectory artifacts."""

    source_artifact_id: str
    target_artifact_id: str
    relation_type: str
    span_index: int = -1
    span_id: str = ""
    trace_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class TrajectoryContext:
    """In-memory accumulator for a single trajectory evaluation.

    Usage inside the span loop::

        ctx = TrajectoryContext(policy_text, tool_definitions)

        for n, span_dict in enumerate(evaluable_spans):
            intent_ctx = ctx.retrieve_for_intent_recognition(span_dict)
            relevancy_ctx = ctx.retrieve_for_relevancy(span_dict)

            # ... call MCE with appropriate context per metric ...

            ctx.ingest_span(span_dict, span_index=n)
    """

    def __init__(
        self,
        policy_text: str,
        tool_definitions: Any = None,
        *,
        recency_window: int = 5,
        max_context_chars: int = 6000,
        coordination_context: CoordinationContext | Dict[str, Any] | None = None,
        adapter_ingestion: str = "eager",
    ):
        if adapter_ingestion not in {"eager", "incremental"}:
            raise ValueError("adapter_ingestion must be 'eager' or 'incremental'")
        self.evidence: List[EvidenceFact] = []
        self.intents: List[IntentEntry] = []
        self.claims: List[ClaimEntry] = []
        self.coordination_events: List[CoordinationEvent] = []
        self.provenance_links: List[ArtifactProvenanceLink] = []
        # Deterministic state for rules about who owns and does which work.
        self.agents: Dict[str, AgentProfile] = {}
        self.work_units: List[WorkUnit] = []
        self.flags: List[FlagEntry] = []
        self.delivery_span_index = -1
        self.termination_span_index = -1
        # ``eager`` keeps the historical behavior of ingesting a coordination
        # sidecar at construction. ``incremental`` defers each edge to the span
        # it came from, so no state exists before the work that produced it.
        self.adapter_ingestion = adapter_ingestion
        self._pending_adapter_edges: List[Any] = []
        self._span_index_by_id: Dict[str, int] = {}
        self._span_timestamps: List[tuple[int, str]] = []
        self._pending_tool_requesters: Dict[str, str] = {}
        # Replies relayed to an allocator (delegation tool output or sidecar
        # response), held until the allocator takes control back.
        self._pending_relays: Dict[str, Dict[str, Any]] = {}
        # Routing fields read from a node's state, keyed by target agent, held
        # until a router output or the target's own span confirms them.
        self._state_routes: Dict[str, Dict[str, Any]] = {}
        self._adapter_verification_ingested = False
        # Tool-call id -> requesting agent, when an LLM output names its calls.
        self._tool_call_requesters: Dict[str, str] = {}
        self._latest_llm_agent_id = ""
        self._finalized = False
        self._roster_complete = False
        self._node_replies: Dict[str, str] = {}
        self.latest_root_answer = ""
        self.latest_root_answer_span_index = -1
        self.root_agent_id = ""
        # The request the trajectory was started with (the workflow input).
        self.root_request = ""
        self.coordination_context = (
            coordination_context
            if isinstance(coordination_context, CoordinationContext)
            else CoordinationContext.from_payload(coordination_context)
        )
        self.coordination_metadata: Dict[str, Any] = {}
        self._span_artifact_ids: Dict[str, List[str]] = {}
        self._span_agent_ids: Dict[str, str] = {}
        self._span_coordination_event_types: Dict[str, set[str]] = {}
        self._latest_claim_by_agent: Dict[str, str] = {}

        self.policy_text = policy_text.strip() if policy_text else ""
        self.tool_definitions = tool_definitions
        self.recency_window = recency_window
        self.max_context_chars = max_context_chars

        if self.policy_text:
            self.add_policy_rule(self.policy_text, source_name="policy")

        self._ingest_adapter_coordination_context()

    def add_policy_rule(
        self,
        content: str,
        *,
        source_name: str = "policy",
        span_index: int = -1,
    ) -> None:
        """Persist one source-labelled policy or semantic contract."""
        normalized = content.strip() if content else ""
        if not normalized:
            return
        if any(
            fact.fact_type == "policy_rule"
            and fact.source_name == source_name
            and fact.content == normalized
            for fact in self.evidence
        ):
            return
        fact = EvidenceFact(
            span_index=span_index,
            fact_type="policy_rule",
            content=normalized,
            source_name=source_name,
            agent_id=(
                source_name.split(":", 1)[1]
                if source_name.startswith("semantic_contract:")
                else ""
            ),
        )
        artifact_id = self._append_evidence(fact)
        self._register_contract(fact, artifact_id)

    def _split_contract_prefix(self, text: str) -> tuple[str, str]:
        """Split a known contract off the start of a prompt message.

        Returns ``(contract_artifact_id, remainder)``; the id is empty when the
        message does not start with a recorded contract.
        """
        normalized = " ".join(str(text or "").split())
        best_id, best_len = "", 0
        for index, fact in enumerate(self.evidence):
            if fact.fact_type != "policy_rule":
                continue
            contract = " ".join(fact.content.split())
            if len(contract) >= 80 and normalized.startswith(contract):
                if len(contract) > best_len:
                    best_id = self._evidence_artifact_id(index, fact)
                    best_len = len(contract)
        if not best_id:
            return "", str(text or "")
        return best_id, normalized[best_len:].strip()

    def _ingest_adapter_coordination_context(self) -> None:
        """Normalize an adapter sidecar into the canonical coordination model."""
        context = self.coordination_context
        selected_topology = (
            context.inferred_topology
            if context.inferred_topology != "unknown"
            else context.declared_topology
        )
        if selected_topology:
            self.coordination_metadata.setdefault("topology", selected_topology)
        self.coordination_metadata.setdefault(
            "topology_provenance",
            {
                "declared": context.declared_topology,
                "declared_source": context.declared_topology_source,
                "inferred": context.inferred_topology,
                "verification": context.topology_verification,
                "confidence": context.inference_confidence,
                "method": context.inference_method,
                "signals": list(context.inference_signals),
                "ambiguities": list(context.inference_ambiguities),
            },
        )
        for edge in context.edges:
            for agent_id in (edge.dispatcher, edge.sender, edge.receiver):
                self.declare_agent(agent_id, declared_by="adapter_edge")

        if self.adapter_ingestion == "incremental":
            self._pending_adapter_edges = list(context.edges)
            return

        for edge in context.edges:
            span_index = (
                edge.start_event_index
                if edge.start_event_index >= 0
                else max(edge.stage_index - 1, -1)
            )
            self._ingest_adapter_edge(edge, span_index)
        self._ingest_adapter_verification()
        if context.final_response:
            self.set_final_answer(
                context.final_response,
                context.final_response_event_index,
                record_synthesis=True,
            )

    def _ingest_adapter_edge(self, edge: Any, span_index: int) -> None:
        """Convert one sidecar delegation edge into events and a work unit."""
        relation = edge.relation.casefold()
        if relation == "critique":
            event_types = [
                "assignment",
                "handoff",
                "peer_message",
                "revision",
            ]
        else:
            event_types = ["assignment", "handoff"]

        source_span_ids = [str(span_id) for span_id in edge.source_span_ids if span_id]
        span_id = source_span_ids[0] if source_span_ids else ""
        actor_agent_id = (
            edge.dispatcher if edge.dispatcher != "unknown" else edge.sender
        )
        if actor_agent_id == "unknown":
            actor_agent_id = ""
        sender_agent_ids = [
            value for value in [edge.sender] if value and value != "unknown"
        ]
        recipient_agent_ids = [
            value for value in [edge.receiver] if value and value != "unknown"
        ]
        span_dict: Dict[str, Any] = {
            "span_id": span_id,
            "agent_id": actor_agent_id,
            "entity_name": edge.call_id or edge.edge_id or relation,
            "input_payload": {"task": edge.request} if edge.request else {},
            "output_payload": ({"content": edge.response} if edge.response else {}),
        }
        assignment_intent_ids: List[str] = []
        if any(event_type in {"assignment", "handoff"} for event_type in event_types):
            assignment_intent_ids = self._ensure_assignment_intent(
                span_dict,
                span_index,
                event_type=event_types[0],
                parent_intent_ids=[],
                recipient_agent_ids=recipient_agent_ids,
            )
        unit = self._open_work_unit(
            allocator_agent_id=actor_agent_id,
            recipient_agent_ids=recipient_agent_ids,
            request=edge.request,
            span_index=span_index,
            source="adapter",
            call_id=edge.call_id,
            edge_id=edge.edge_id,
            source_event_index=(
                edge.start_event_index if edge.start_event_index >= 0 else None
            ),
            source_span_ids=source_span_ids,
            intent_ids=assignment_intent_ids,
        )

        content = _safe_json(
            {
                "request": edge.request,
                "response": edge.response,
            },
            max_len=None,
        )
        for event_type in event_types:
            event = CoordinationEvent(
                event_id=f"coordination:{len(self.coordination_events)}",
                span_index=span_index,
                event_type=event_type,
                operation_name=edge.call_id or edge.edge_id or relation,
                actor_agent_id=actor_agent_id,
                sender_agent_ids=sender_agent_ids,
                recipient_agent_ids=recipient_agent_ids,
                related_intent_ids=list(assignment_intent_ids),
                linked_span_ids=source_span_ids,
                link_types=[relation],
                assignment_mode=("dynamic" if event_type == "assignment" else relation),
                status="completed" if edge.response else "observed",
                content=content,
                phase=(f"stage_{edge.stage_index}" if edge.stage_index else ""),
                round_index=edge.round_index,
                span_id=span_id,
                work_id=unit.work_id if unit else "",
                source_event_index=(
                    edge.start_event_index if edge.start_event_index >= 0 else None
                ),
            )
            self.coordination_events.append(event)
            if unit is not None:
                unit.assignment_event_ids.append(event.event_id)
                self._add_provenance_link(
                    event.event_id,
                    unit.work_id,
                    "assigns" if event_type == "assignment" else "communicates",
                    span_dict=span_dict,
                    span_index=span_index,
                )
            for source_span_id in source_span_ids:
                source_span = dict(span_dict)
                source_span["span_id"] = source_span_id
                self._remember_span(source_span, event.event_id)
                self._span_coordination_event_types.setdefault(
                    source_span_id,
                    set(),
                ).add(event_type)
            self._record_coordination_on_intents(
                event,
                assignment_intent_ids=assignment_intent_ids,
            )
        if unit is not None and edge.response:
            if self.adapter_ingestion == "eager":
                self._resolve_work_response(
                    unit,
                    edge.response,
                    span_index,
                    basis="adapter_response",
                )
            else:
                self._hold_relay(
                    unit,
                    edge.response,
                    span_index,
                    basis="adapter_response",
                    agent_id=recipient_agent_ids[0] if recipient_agent_ids else "",
                )

    def _ingest_adapter_verification(self, span_index: Optional[int] = None) -> None:
        context = self.coordination_context
        verification = context.verification
        if verification is None:
            return
        source_edge = next(
            (edge for edge in context.edges if edge.edge_id == verification.edge_id),
            None,
        )
        source_span_ids = (
            [str(span_id) for span_id in source_edge.source_span_ids if span_id]
            if source_edge is not None
            else []
        )
        span_id = source_span_ids[0] if source_span_ids else ""
        related_intent_ids = _ordered_union(
            [],
            [
                intent_id
                for event in self.coordination_events
                if event.span_id == span_id
                for intent_id in event.related_intent_ids
            ],
        )
        native_index = (
            source_edge.end_event_index
            if source_edge is not None and source_edge.end_event_index >= 0
            else max(verification.stage_index - 1, -1)
        )
        event = CoordinationEvent(
            event_id=f"coordination:{len(self.coordination_events)}",
            span_index=native_index if span_index is None else span_index,
            event_type="verification",
            operation_name=(
                source_edge.call_id
                if source_edge is not None and source_edge.call_id
                else verification.edge_id
            ),
            actor_agent_id=verification.receiver,
            sender_agent_ids=[verification.receiver],
            recipient_agent_ids=[verification.dispatcher],
            related_intent_ids=related_intent_ids,
            linked_span_ids=source_span_ids,
            link_types=["verification"],
            status=verification.verdict.casefold(),
            content=_safe_json(
                {
                    "verdict": verification.verdict,
                    "action_after_verification": (
                        verification.action_after_verification
                    ),
                    "verification_gate_observed": (
                        verification.verification_gate_observed
                    ),
                },
                max_len=None,
            ),
            phase=(
                f"stage_{verification.stage_index}" if verification.stage_index else ""
            ),
            round_index=verification.round_index,
            span_id=span_id,
            source_event_index=native_index if native_index >= 0 else None,
        )
        self.coordination_events.append(event)
        for source_span_id in source_span_ids:
            source_span = {
                "span_id": source_span_id,
                "agent_id": verification.receiver,
            }
            self._remember_span(source_span, event.event_id)
            self._span_coordination_event_types.setdefault(
                source_span_id,
                set(),
            ).add("verification")
        self._record_coordination_on_intents(event)

    def set_final_answer(
        self,
        text: str,
        span_index: int,
        *,
        record_synthesis: bool = False,
    ) -> None:
        """Record an explicitly identified final synthesis."""
        normalized = str(text or "").strip()
        if not normalized:
            return
        self.latest_root_answer = normalized
        self.latest_root_answer_span_index = span_index
        if record_synthesis:
            self._record_final_synthesis(normalized, span_index)

    # ------------------------------------------------------------------
    # Agents, work units and flags
    # ------------------------------------------------------------------

    def declare_agent(
        self,
        agent_id: str,
        *,
        span_index: int = -1,
        declared_by: str = "trace_scan",
    ) -> Optional[AgentProfile]:
        """Register an agent the trajectory declares or shows."""
        agent_id = str(agent_id or "").strip()
        if not agent_id or agent_id.casefold() in {"unknown", "none", "null"}:
            return None
        profile = self.agents.get(agent_id)
        if profile is None:
            profile = AgentProfile(agent_id=agent_id, first_seen=span_index)
            self.agents[agent_id] = profile
        elif span_index >= 0 and (
            profile.first_seen < 0 or span_index < profile.first_seen
        ):
            profile.first_seen = span_index
        if declared_by and declared_by not in profile.declared_by:
            profile.declared_by.append(declared_by)
        return profile

    def declare_root_request(self, text: str) -> None:
        """Record the request the run was started with, read from its input."""
        self.root_request = str(text or "").strip()

    def declare_roster(self, agents: List[tuple[str, int]]) -> None:
        """Declare the complete roster seen in a trace before ingestion.

        Only identities are declared (a names-only scan, like reading a graph
        definition); no state from later spans becomes visible. A declared
        roster lets router outputs and inferred recipients be validated.
        """
        for agent_id, span_index in agents:
            self.declare_agent(agent_id, span_index=span_index)
        self._roster_complete = bool(self.agents)

    def finalize_state(self) -> None:
        """Close the trajectory: flush deferred adapter state, resolve work."""
        if self._finalized:
            return
        self._finalized = True
        for edge in list(self._pending_adapter_edges):
            self._ingest_adapter_edge(edge, self._span_index_for_timestamp(edge))
        self._pending_adapter_edges = []
        for target in list(self._state_routes):
            self._open_state_route(target)
        if (
            self.adapter_ingestion == "incremental"
            and self.coordination_context.verification is not None
            and not self._adapter_verification_ingested
        ):
            self._adapter_verification_ingested = True
            self._ingest_adapter_verification(span_index=self._last_span_index())
        boundary = self.latest_root_answer_span_index
        for unit in self.work_units:
            if unit.outcome != "pending":
                continue
            relay = self._pending_relays.get(unit.work_id)
            if relay is not None:
                self._apply_relay(
                    unit,
                    max([relay["span_index"], *unit.receipt_span_indices]),
                )
                continue
            if unit.receipt_span_indices:
                reply, claim_id = self._latest_recipient_reply(unit)
                if reply:
                    self._resolve_work_response(
                        unit,
                        reply,
                        max(unit.receipt_span_indices),
                        basis="final_recipient_reply",
                        response_ids=[claim_id] if claim_id else [],
                    )
                    continue
                self._set_work_outcome(
                    unit,
                    "unfinished",
                    basis="received_not_resolved_by_boundary",
                    span_index=boundary,
                )
            else:
                self._set_work_outcome(
                    unit,
                    "no_response",
                    basis="not_received_by_boundary",
                    span_index=boundary,
                )
        for profile in self.agents.values():
            profile.active = bool(
                profile.llm_span_count
                or profile.tool_span_count
                or profile.allocated_work_ids
            )
        self.delivery_span_index = boundary

    def span_index_for_text(self, text: str) -> int:
        """Return the latest loop span whose claim emitted ``text``, or -1."""

        def normalize(value: str) -> str:
            visible = re.sub(
                r"<\|?channel\|?>\s*(?:thought|analysis|final)?",
                " ",
                str(value or ""),
                flags=re.IGNORECASE,
            )
            return " ".join(visible.split()).casefold()

        target = normalize(text)
        if not target:
            return -1
        probe = target[:400]
        for claim in reversed(self.claims):
            content = normalize(claim.content)
            if content and (
                probe in content
                or (content in target and len(content) >= 0.5 * len(target))
            ):
                return claim.span_index
        return -1

    def _last_span_index(self) -> int:
        return self._span_timestamps[-1][0] if self._span_timestamps else -1

    def _span_index_for_timestamp(self, edge: Any) -> int:
        """Map an adapter edge with no surviving source span onto the loop."""
        start = getattr(edge, "start_timestamp", None)
        target = _timestamp_ns(start)
        if target is not None:
            candidates = [
                index
                for index, stamp in self._span_timestamps
                if stamp is not None and stamp <= target
            ]
            if candidates:
                return max(candidates)
        return self._last_span_index()

    def _known_agent_id(self, value: Any) -> str:
        """Return the roster id matching ``value``, or ``""``."""
        text = str(value or "").strip().strip("\"'")
        wanted = _normalise_actor_id(text)
        if not wanted:
            return ""
        for agent_id in self.agents:
            if _normalise_actor_id(agent_id) == wanted:
                return agent_id
        head = _normalise_actor_id(text.split(".")[0])
        for agent_id in self.agents:
            if _normalise_actor_id(agent_id) == head:
                return agent_id
        return ""

    def _explicit_agent_id(self, span_dict: Dict[str, Any]) -> str:
        """Return the span's agent without falling back to an app/service name."""
        value = str(span_dict.get("agent_id") or "").strip()
        if value and value.casefold() not in {"unknown", "none", "null"}:
            return value
        attrs = _span_attributes(span_dict)
        for key in ("mas.agent.id", "agent.id"):
            value = str(attrs.get(key) or "").strip()
            if value and value.casefold() != "unknown":
                return value
        raw_span = span_dict.get("raw_span_data")
        raw_span = raw_span if isinstance(raw_span, dict) else {}
        service = str(span_dict.get("app_name") or raw_span.get("ServiceName") or "")
        if service and service in self.agents:
            return service
        return ""

    def _observe_agent_span(
        self,
        span_dict: Dict[str, Any],
        span_index: int,
        agent_id: str,
    ) -> None:
        if self._roster_complete and agent_id not in self.agents:
            # Not an agent of the declared roster (e.g. a framework node).
            return
        profile = self.declare_agent(
            agent_id,
            span_index=span_index,
            declared_by="observed",
        )
        if profile is None:
            return
        profile.last_seen = max(profile.last_seen, span_index)
        profile.span_count += 1
        entity_type = span_dict.get("entity_type")
        if entity_type == "llm":
            profile.llm_span_count += 1
            for name in span_dict.get("tool_names") or []:
                if name not in profile.declared_tools:
                    profile.declared_tools.append(str(name))
        elif entity_type == "tool":
            profile.tool_span_count += 1
            name = str(span_dict.get("entity_name") or "")
            if name and name not in profile.observed_tools:
                profile.observed_tools.append(name)

    def _register_contract(self, fact: EvidenceFact, artifact_id: str) -> None:
        """Attach a contract to its agent and read any roster table it holds."""
        agent_id = ""
        if fact.source_name.startswith("semantic_contract:"):
            agent_id = fact.source_name.split(":", 1)[1]
        profile = self.agents.get(agent_id) if agent_id else None
        if profile is not None and artifact_id not in profile.contract_ids:
            profile.contract_ids.append(artifact_id)
        declared: Dict[str, str] = {}
        for match in _CAPABILITY_LINE_RE.finditer(fact.content):
            candidate = self._known_agent_id(match.group("agent"))
            if candidate:
                declared.setdefault(candidate, match.group("capability").strip())
        if not declared:
            # Contracts recovered from repeated headers are whitespace-normalized,
            # so roster tables lose their line breaks; match per known agent.
            flat = " ".join(fact.content.split())
            for candidate in self.agents:
                pattern = re.compile(
                    r"(?:^|\s)[-*\u2022]\s*" + re.escape(candidate) + r"\s*:\s*"
                    r"(?P<capability>.{8,400}?)"
                    r"(?=\s+[-*\u2022]\s+[\w.\-]+\s*:|(?<=[.!?])\s|\s*$)",
                    re.IGNORECASE,
                )
                match = pattern.search(flat)
                if match:
                    declared[candidate] = match.group("capability").strip()
        for candidate, capability in declared.items():
            if candidate == agent_id:
                continue
            target = self.agents[candidate]
            if not target.declared_capability:
                target.declared_capability = capability
                target.declared_capability_source = artifact_id
            if "capability_table" not in target.declared_by:
                target.declared_by.append("capability_table")

    def _open_work_unit(
        self,
        *,
        allocator_agent_id: str,
        recipient_agent_ids: List[str],
        request: str,
        span_index: int,
        source: str,
        call_id: str = "",
        edge_id: str = "",
        source_event_index: Optional[int] = None,
        source_span_ids: Optional[List[str]] = None,
        intent_ids: Optional[List[str]] = None,
    ) -> Optional[WorkUnit]:
        """Open (or join) the unit for one allocation decision."""
        recipients = [str(agent) for agent in recipient_agent_ids if agent]
        allocator = str(allocator_agent_id or "")
        if not recipients:
            return None
        request_text = str(request or "").strip()
        intent_id = next((item for item in intent_ids or [] if item), "")

        def join(unit: WorkUnit) -> WorkUnit:
            unit.source_span_ids = _ordered_union(
                unit.source_span_ids, list(source_span_ids or [])
            )
            if request_text and not unit.request:
                unit.request = request_text
            if intent_id and not unit.intent_id:
                unit.intent_id = intent_id
            if call_id and not unit.call_id:
                unit.call_id = call_id
            if edge_id and not unit.edge_id:
                unit.edge_id = edge_id
            if source_event_index is not None and unit.source_event_index is None:
                unit.source_event_index = source_event_index
            return unit

        if call_id:
            for unit in self.work_units:
                if unit.call_id == call_id:
                    return join(unit)
        carried = set(source_span_ids or [])
        if carried:
            for unit in self.work_units:
                if carried & set(unit.source_span_ids) and set(
                    unit.recipient_agent_ids
                ) == set(recipients):
                    # The same delegation seen from its edge and its span.
                    return join(unit)
        for unit in reversed(self.work_units):
            if (
                unit.outcome == "pending"
                and not unit.receipt_span_indices
                and unit.allocator_agent_id == allocator
                and set(unit.recipient_agent_ids) == set(recipients)
                and (not call_id or not unit.call_id)
            ):
                # The same allocation decision recorded by another span.
                return join(unit)

        unit = WorkUnit(
            work_id=f"work:{len(self.work_units)}",
            allocator_agent_id=allocator,
            recipient_agent_ids=recipients,
            request=request_text,
            request_span_index=span_index,
            source=source,
            call_id=call_id,
            edge_id=edge_id,
            source_event_index=source_event_index,
            source_span_ids=list(source_span_ids or []),
            intent_id=intent_id,
            events=[{"type": "assigned", "span_index": span_index, "source": source}],
        )
        normalized = _normalise_semantic_text(request_text)

        def same_request(previous: WorkUnit) -> bool:
            previous_text = _normalise_semantic_text(previous.request)
            return bool(normalized and previous_text) and (
                normalized == previous_text
                or normalized in previous_text
                or previous_text in normalized
            )

        # Going back to the same recipients after an unresolved attempt is a
        # retry even when the allocator rewords the task.
        same_pair = next(
            (
                previous
                for previous in reversed(self.work_units)
                if previous.allocator_agent_id == allocator
                and set(previous.recipient_agent_ids) == set(recipients)
            ),
            None,
        )
        if same_pair is not None and same_pair.outcome in _RETRYABLE_OUTCOMES:
            unit.retry_of_work_id = same_pair.work_id
            unit.attempt_index = same_pair.attempt_index + 1
            unit.retry_basis = (
                "same_request" if same_request(same_pair) else "same_recipients"
            )
            same_pair.events.append(
                {
                    "type": "retried_by",
                    "work_id": unit.work_id,
                    "span_index": span_index,
                }
            )
        else:
            for previous in reversed(self.work_units):
                if previous.allocator_agent_id != allocator or not same_request(
                    previous
                ):
                    continue
                if set(previous.recipient_agent_ids) != set(recipients):
                    unit.previous_owner_agent_ids = list(previous.recipient_agent_ids)
                    if previous.outcome in _RETRYABLE_OUTCOMES:
                        unit.retry_of_work_id = previous.work_id
                        unit.retry_basis = "same_request"
                    previous.events.append(
                        {
                            "type": "reassigned_to",
                            "work_id": unit.work_id,
                            "recipient_agent_ids": list(recipients),
                            "span_index": span_index,
                        }
                    )
                break
        self.work_units.append(unit)
        if allocator in self.agents:
            self.agents[allocator].allocated_work_ids.append(unit.work_id)
        for recipient in recipients:
            if recipient in self.agents:
                self.agents[recipient].received_work_ids.append(unit.work_id)
        return unit

    def _work_unit_by_id(self, work_id: str) -> Optional[WorkUnit]:
        match = re.fullmatch(r"work:(\d+)", str(work_id or ""))
        if not match:
            return None
        index = int(match.group(1))
        return self.work_units[index] if index < len(self.work_units) else None

    def _work_unit_for_span(
        self,
        span_dict: Dict[str, Any],
        span_index: int,
        agent_id: str,
    ) -> Optional[WorkUnit]:
        """Find the unit a recipient span executes under.

        An explicit call identifier in the span's parent linkage wins (for
        example ``<agent>-<call_id>-exec``); otherwise the most recent pending
        unit addressed to the agent is used.
        """
        if not agent_id:
            return None
        route = self._state_routes.get(agent_id)
        if (
            route is not None
            and route["allocator"] != agent_id
            and route["span_index"] <= span_index
        ):
            unit = self._open_state_route(agent_id)
            if unit is not None:
                return unit
        attrs = _span_attributes(span_dict)
        parent_refs = " ".join(
            str(value or "")
            for value in (
                attrs.get("mas.parent.call.id"),
                span_dict.get("parent_span_id"),
            )
        )
        for unit in reversed(self.work_units):
            if (
                unit.call_id
                and agent_id in unit.recipient_agent_ids
                and re.search(rf"(?<!\w){re.escape(unit.call_id)}(?!\w)", parent_refs)
            ):
                return unit
        for unit in reversed(self.work_units):
            if (
                unit.outcome == "pending"
                and agent_id in unit.recipient_agent_ids
                and agent_id != unit.allocator_agent_id
                and unit.request_span_index <= span_index
                and not unit.call_id
            ):
                return unit
        return None

    def _open_state_route(self, target: str) -> Optional[WorkUnit]:
        """Open the unit a node's routing state named for ``target``."""
        route = self._state_routes.pop(target, None)
        if route is None:
            return None
        allocator = route["allocator"]
        self._ingest_coordination_span(
            route["span_dict"],
            route["span_index"],
            additional_event_types=["assignment"],
            recipient_override=[target],
            actor_override=allocator,
            only_event_types={"assignment"},
        )
        return next(
            (
                unit
                for unit in reversed(self.work_units)
                if unit.outcome == "pending"
                and unit.allocator_agent_id == allocator
                and target in unit.recipient_agent_ids
            ),
            None,
        )

    def _record_receipt(self, unit: WorkUnit, span_index: int) -> None:
        if span_index in unit.receipt_span_indices:
            return
        if not unit.receipt_span_indices:
            unit.events.append({"type": "received", "span_index": span_index})
        unit.receipt_span_indices.append(span_index)

    def _latest_recipient_reply(self, unit: WorkUnit) -> tuple[str, str]:
        for index in range(len(self.claims) - 1, -1, -1):
            claim = self.claims[index]
            if (
                claim.work_id == unit.work_id
                and claim.agent_id in unit.recipient_agent_ids
                and claim.claim_type != "tool_result"
                and _has_visible_content(claim.content)
                and not _is_tool_call_only(claim.content)
            ):
                return claim.content, f"claim:{index}"
        return self._node_replies.get(unit.work_id, ""), ""

    def _set_work_outcome(
        self,
        unit: WorkUnit,
        outcome: str,
        *,
        basis: str,
        span_index: int,
    ) -> None:
        unit.outcome = outcome
        unit.outcome_basis = basis
        unit.outcome_span_index = span_index
        unit.events.append(
            {
                "type": "resolved",
                "outcome": outcome,
                "basis": basis,
                "span_index": span_index,
            }
        )
        for event in self.coordination_events:
            if event.event_id in unit.assignment_event_ids and not event.outcome:
                event.outcome = outcome
        intent = self._intent_by_artifact_id(unit.intent_id)
        if intent is not None:
            intent.events.append(
                {
                    "span_index": span_index,
                    "type": "work_outcome",
                    "work_id": unit.work_id,
                    "outcome": outcome,
                    "basis": basis,
                }
            )

    def _resolve_work_response(
        self,
        unit: WorkUnit,
        text: str,
        span_index: int,
        *,
        basis: str,
        response_ids: Optional[List[str]] = None,
        contains_error: bool = False,
        response_span_index: Optional[int] = None,
    ) -> None:
        """Classify a reply to a unit and resolve the unit once."""
        unit.response_artifact_ids = _ordered_union(
            unit.response_artifact_ids, list(response_ids or [])
        )
        if unit.outcome != "pending":
            return
        outcome, kind = _classify_work_response(text, contains_error=contains_error)
        unit.response_span_index = (
            span_index if response_span_index is None else response_span_index
        )
        self._set_work_outcome(
            unit,
            outcome,
            basis=f"{basis}:{kind}",
            span_index=span_index,
        )

    def _hold_relay(
        self,
        unit: WorkUnit,
        text: str,
        span_index: int,
        *,
        basis: str,
        agent_id: str,
        response_ids: Optional[List[str]] = None,
        contains_error: bool = False,
        artifact_id: str = "",
    ) -> None:
        """Keep a relayed reply until the allocator takes control back.

        A delegation span starts before the recipient's own spans, so its
        output (the recipient's final reply) is known before the recipient has
        run. Resolving the unit then would close it before its receipts.
        """
        unit.response_artifact_ids = _ordered_union(
            unit.response_artifact_ids, list(response_ids or [])
        )
        if unit.outcome != "pending":
            return
        relay = self._pending_relays.get(unit.work_id)
        if relay is None:
            self._pending_relays[unit.work_id] = {
                "text": text,
                "span_index": span_index,
                "basis": basis,
                "agent_id": agent_id,
                "response_ids": list(response_ids or []),
                "contains_error": contains_error,
                "artifact_id": artifact_id,
            }
            return
        relay["response_ids"] = _ordered_union(
            relay["response_ids"], list(response_ids or [])
        )
        relay["artifact_id"] = relay["artifact_id"] or artifact_id

    def _apply_relay(self, unit: WorkUnit, span_index: int) -> bool:
        """Resolve ``unit`` from its held relay; False when there is none."""
        relay = self._pending_relays.pop(unit.work_id, None)
        if relay is None:
            return False
        verification = self.coordination_context.verification
        if (
            self.adapter_ingestion == "incremental"
            and not self._adapter_verification_ingested
            and verification is not None
            and unit.edge_id
            and unit.edge_id == verification.edge_id
        ):
            self._adapter_verification_ingested = True
            self._ingest_adapter_verification(span_index=span_index)
        self._record_flags(
            relay["text"],
            span_index=relay["span_index"],
            agent_id=relay["agent_id"],
            artifact_id=relay["artifact_id"],
            work_id=unit.work_id,
        )
        self._resolve_work_response(
            unit,
            relay["text"],
            span_index,
            basis=relay["basis"],
            response_ids=relay["response_ids"],
            contains_error=relay["contains_error"],
            response_span_index=relay["span_index"],
        )
        return True

    def _close_returned_work(self, allocator_agent_id: str, span_index: int) -> None:
        """Resolve units whose recipient handed control back to the allocator."""
        if not allocator_agent_id:
            return
        for unit in self.work_units:
            if (
                unit.outcome != "pending"
                or unit.allocator_agent_id != allocator_agent_id
            ):
                continue
            last_receipt = max(unit.receipt_span_indices, default=-1)
            relay = self._pending_relays.get(unit.work_id)
            if relay is not None:
                if relay["span_index"] < span_index and last_receipt < span_index:
                    self._apply_relay(unit, span_index)
                continue
            if last_receipt < 0 or last_receipt >= span_index:
                continue
            reply, claim_id = self._latest_recipient_reply(unit)
            if reply:
                self._resolve_work_response(
                    unit,
                    reply,
                    span_index,
                    basis="control_returned",
                    response_ids=[claim_id] if claim_id else [],
                )
            else:
                self._set_work_outcome(
                    unit,
                    "no_response",
                    basis="control_returned_without_reply",
                    span_index=span_index,
                )

    def _record_flags(
        self,
        text: str,
        *,
        span_index: int,
        agent_id: str,
        artifact_id: str,
        work_id: str,
    ) -> None:
        for kind, quote in _flag_matches(text):
            if any(
                flag.agent_id == agent_id
                and flag.kind == kind
                and flag.quote == quote
                and flag.work_id == work_id
                for flag in self.flags
            ):
                # The same statement seen again, e.g. relayed by the
                # delegation tool after the recipient said it.
                continue
            self.flags.append(
                FlagEntry(
                    flag_id=f"flag:{len(self.flags)}",
                    span_index=span_index,
                    agent_id=agent_id,
                    kind=kind,
                    quote=quote,
                    artifact_id=artifact_id,
                    work_id=work_id,
                )
            )

    def _route_target(self, span_dict: Dict[str, Any]) -> tuple[str, bool, bool]:
        """Return ``(recipient, terminal, from_state)`` for a routing choice.

        A router node's bare output (``"schedule_agent"``) is a decision. A
        routing field inside a larger state object (``next_agent``) is
        reported with ``from_state=True`` because node outputs can carry a
        stale value.
        """
        if not self._roster_complete:
            return "", False, False
        output = span_dict.get("output_payload")
        value: Any = None
        from_state = False
        if isinstance(output, str):
            value = output
        elif isinstance(output, dict):
            for key in ("outputs", "output", "value"):
                candidate = output.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    value = candidate
                    break
            if value is None:
                for key in ("next_agent", "next", "goto", "route"):
                    candidate = output.get(key)
                    if isinstance(candidate, str) and candidate.strip():
                        value = candidate
                        from_state = True
                        break
        if not isinstance(value, str):
            return "", False, False
        token = value.strip().strip("\"'")
        if token.casefold() in _TERMINAL_ROUTES:
            return "", True, from_state
        if not token or len(token) > 80 or re.search(r"\s", token):
            return "", False, from_state
        return self._known_agent_id(token), False, from_state

    def _is_pending_recipient(self, agent_id: str) -> bool:
        return bool(agent_id) and any(
            unit.outcome == "pending"
            and agent_id in unit.recipient_agent_ids
            and agent_id != unit.allocator_agent_id
            for unit in self.work_units
        )

    def _handback_unit(self, returning_agent: str, target: str) -> Optional[WorkUnit]:
        """The unit ``returning_agent`` hands back to its allocator ``target``.

        A resolved unit also counts: a second route back to the allocator is
        the same handback, not the recipient assigning work to its allocator.
        """
        candidates = [
            unit
            for unit in reversed(self.work_units)
            if unit.allocator_agent_id == target
            and returning_agent in unit.recipient_agent_ids
        ]
        pending = [unit for unit in candidates if unit.outcome == "pending"]
        return (pending or candidates or [None])[0]

    def _message_targets(
        self,
        agent_text: str,
        output_payload: Any,
        actor_agent_id: str,
    ) -> List[tuple[str, str]]:
        """Return ``(recipient, message)`` for typed messages addressed to agents."""
        if not self._roster_complete:
            return []
        candidates: List[Any] = [output_payload]
        stripped = str(agent_text or "").strip()
        if stripped.startswith("{"):
            try:
                candidates.append(json.loads(stripped))
            except (TypeError, json.JSONDecodeError):
                pass
        targets: List[tuple[str, str]] = []
        stack = list(candidates)
        while stack:
            current = stack.pop()
            if isinstance(current, list):
                stack.extend(current)
                continue
            if not isinstance(current, dict):
                continue
            for key in ("target", "recipient", "to"):
                value = current.get(key)
                if not isinstance(value, str):
                    continue
                if not any(
                    field in current for field in ("message", "content", "type")
                ):
                    continue
                recipient = self._known_agent_id(value)
                if recipient and recipient != actor_agent_id:
                    message = current.get("message") or current.get("content") or ""
                    targets.append((recipient, _message_content(message)))
            stack.extend(
                value for value in current.values() if isinstance(value, (dict, list))
            )
        unique: List[tuple[str, str]] = []
        for item in targets:
            if item[0] not in {existing[0] for existing in unique}:
                unique.append(item)
        return unique

    # ------------------------------------------------------------------
    # Ingestion: called after each span is evaluated
    # ------------------------------------------------------------------

    def ingest_span(self, span_dict: Dict[str, Any], span_index: int) -> None:
        """Extract and store information from a processed span."""
        entity_type = span_dict.get("entity_type", "")
        entity_name = span_dict.get("entity_name", "unknown")
        span_id = str(span_dict.get("span_id") or "")
        if span_id:
            self._span_index_by_id.setdefault(span_id, span_index)
        self._span_timestamps.append(
            (span_index, _timestamp_ns(span_dict.get("timestamp")))
        )
        if self._pending_adapter_edges and span_id:
            due = [
                edge
                for edge in self._pending_adapter_edges
                if span_id in {str(item) for item in edge.source_span_ids}
            ]
            for edge in due:
                self._pending_adapter_edges.remove(edge)
                self._ingest_adapter_edge(edge, span_index)

        if entity_type == "tool":
            self._ingest_tool_span(span_dict, span_index, entity_name)
        elif entity_type == "llm":
            self._ingest_llm_span(span_dict, span_index, entity_name)
        else:
            self._remember_span(span_dict)
            explicit_agent = self._explicit_agent_id(span_dict)
            if explicit_agent:
                self._observe_agent_span(span_dict, span_index, explicit_agent)
                unit = self._work_unit_for_span(span_dict, span_index, explicit_agent)
                if unit is not None:
                    self._record_receipt(unit, span_index)
                    node_output = span_dict.get("output_payload")
                    reply = (
                        _extract_agent_output(node_output)
                        if isinstance(node_output, dict)
                        else str(node_output or "")
                    )
                    if (
                        reply
                        and _has_visible_content(reply)
                        and not _is_tool_call_only(reply)
                    ):
                        # Some frameworks surface an agent's reply only on its
                        # node span, never as a separate LLM completion.
                        self._node_replies[unit.work_id] = reply
                for tool_name in _requested_tool_names(span_dict.get("output_payload")):
                    self._pending_tool_requesters[tool_name] = explicit_agent
                for tool_call_id in _requested_tool_call_ids(
                    span_dict.get("output_payload")
                ):
                    self._tool_call_requesters[tool_call_id] = explicit_agent
            event_types = _coordination_event_types(
                span_dict,
                _span_links(span_dict),
            )
            extra_types: List[str] = []
            recipient_override: Optional[List[str]] = None
            actor_override = ""
            suppressed: set[str] = set()
            target, terminal, from_state = self._route_target(span_dict)
            allocator = explicit_agent or self._latest_llm_agent_id
            if from_state and self._is_pending_recipient(allocator):
                # A recipient's node state is not a decision to hand work back
                # or re-route; the router output or the allocator's next turn is.
                target, terminal = "", False
            if terminal:
                self.termination_span_index = span_index
                suppressed = {"assignment", "handoff"}
            elif target:
                handback = self._handback_unit(allocator, target)
                if handback is not None:
                    if not self._apply_relay(handback, span_index):
                        reply, claim_id = self._latest_recipient_reply(handback)
                        self._resolve_work_response(
                            handback,
                            reply,
                            span_index,
                            basis="handback_route",
                            response_ids=[claim_id] if claim_id else [],
                        )
                    suppressed = {"assignment", "handoff"}
                elif target != allocator and from_state:
                    # A node span starts before the decision turn it wraps, so
                    # its state names the next agent before the allocator's
                    # reasoning is ingested. Wait for the router output or the
                    # target's first span to open the unit.
                    self._state_routes[target] = {
                        "allocator": allocator,
                        "span_index": span_index,
                        "span_dict": span_dict,
                    }
                elif target != allocator:
                    self._state_routes.pop(target, None)
                    extra_types = ["assignment"]
                    recipient_override = [target]
                    actor_override = allocator
            output_artifact_ids: List[str] = []
            if "synthesis" in event_types:
                final_answer = _extract_agent_output(
                    span_dict.get("output_payload") or {}
                )
                if final_answer:
                    self.set_final_answer(final_answer, span_index)
                    output_artifact_ids.append("final_answer")
            self._ingest_coordination_span(
                span_dict,
                span_index,
                output_artifact_ids=output_artifact_ids,
                additional_event_types=extra_types,
                recipient_override=recipient_override,
                actor_override=actor_override,
                suppressed_event_types=suppressed,
            )

    def _ingest_tool_span(
        self, span_dict: Dict[str, Any], span_index: int, tool_name: str
    ) -> None:
        """Index tool input+output as authoritative evidence."""
        input_payload = span_dict.get("input_payload")
        output_payload = span_dict.get("output_payload")
        explicit_agent = self._explicit_agent_id(span_dict)
        if not explicit_agent:
            tool_call_id = _span_call_id(span_dict)
            requester = (
                self._tool_call_requesters.pop(tool_call_id, "") if tool_call_id else ""
            ) or self._pending_tool_requesters.get(tool_name, "")
            if requester:
                # Frameworks often run tools in a separate node with no agent
                # attribute; the agent whose LLM call requested the tool owns it.
                span_dict = {**span_dict, "agent_id": requester}
                explicit_agent = requester
        if explicit_agent:
            self._observe_agent_span(span_dict, span_index, explicit_agent)
        work_unit = self._work_unit_for_span(span_dict, span_index, explicit_agent)
        if work_unit is not None:
            self._record_receipt(work_unit, span_index)
        tool_outcome = _tool_outcome(span_dict, output_payload)
        provenance = self._operation_provenance(span_dict)
        # Only the work item this span executes under is a known link.
        related_intent_ids = (
            [work_unit.intent_id]
            if work_unit is not None and work_unit.intent_id
            else []
        )

        parts: List[str] = [f"[Tool: {tool_name}]"]
        if input_payload:
            parts.append(f"  Called with: {_safe_json(input_payload, max_len=None)}")
        if output_payload:
            parts.append(f"  Returned: {_safe_json(output_payload, max_len=None)}")

        content = "\n".join(parts)
        work_id = work_unit.work_id if work_unit is not None else ""
        if content.strip():
            evidence_id = self._append_evidence(
                EvidenceFact(
                    span_index=span_index,
                    fact_type="tool_output",
                    content=content,
                    source_name=tool_name,
                    related_intent_ids=related_intent_ids,
                    work_id=work_id,
                    outcome=tool_outcome,
                    started_at_ns=_timestamp_ns(span_dict.get("timestamp")),
                    duration_ns=_span_duration_ns(span_dict),
                    **provenance,
                )
            )
        else:
            evidence_id = ""

        claim_id = self._append_claim(
            ClaimEntry(
                span_index=span_index,
                claim_type="tool_result",
                content=(
                    f"Tool '{tool_name}' executed. "
                    f"{_safe_json(output_payload, max_len=None)}"
                ),
                entity_name=tool_name,
                related_intent_ids=related_intent_ids,
                evidence_refs=[evidence_id] if evidence_id else [],
                work_id=work_id,
                outcome=tool_outcome,
                **provenance,
            )
        )
        if evidence_id:
            self._add_provenance_link(
                evidence_id,
                claim_id,
                "supports",
                span_dict=span_dict,
                span_index=span_index,
            )
        self._link_artifacts_to_intents(
            [artifact_id for artifact_id in (evidence_id, claim_id) if artifact_id],
            related_intent_ids,
            span_dict=span_dict,
            span_index=span_index,
        )
        self._remember_span(span_dict, evidence_id, claim_id)
        self._ingest_coordination_span(
            span_dict,
            span_index,
            input_artifact_ids=[evidence_id] if evidence_id else [],
            output_artifact_ids=[claim_id],
            related_intent_ids=related_intent_ids,
        )

        # A delegation tool returns the recipient's reply to the allocator:
        # mark the relay and resolve the unit it carried.
        span_id = str(span_dict.get("span_id") or "")
        delegated = [
            unit
            for unit in self.work_units
            if span_id and span_id in unit.source_span_ids
        ]
        if delegated:
            unit = delegated[-1]
            fact = self.evidence[-1] if evidence_id else None
            claim = self.claims[-1]
            recipient = unit.recipient_agent_ids[0] if unit.recipient_agent_ids else ""
            for artifact in (fact, claim):
                if artifact is None:
                    continue
                artifact.work_id = unit.work_id
                artifact.relayed_from_agent_id = recipient
            reply_text = _tool_reply_text(output_payload)
            self._hold_relay(
                unit,
                reply_text,
                span_index,
                basis="delegation_tool_output",
                agent_id=recipient,
                response_ids=[item for item in (evidence_id, claim_id) if item],
                contains_error=tool_outcome == "error",
                artifact_id=claim_id,
            )

    def _ingest_tool_exchanges(
        self,
        span_dict: Dict[str, Any],
        span_index: int,
        input_payload: Dict[str, Any],
    ) -> None:
        """Record tool results that a chat prompt carries as tool evidence.

        Chat messages replay each tool call and its ``role: tool`` reply, so the
        evidence exists even when the tool ran in a span this evaluator does not
        see (or one that is not exported as a separate tool span). Results
        already recorded from a tool span are not added twice.
        """
        messages = input_payload.get("messages")
        if not isinstance(messages, list):
            return
        calls: Dict[str, tuple[str, Any]] = {}
        for message in messages:
            if not isinstance(message, dict):
                continue
            for call in message.get("tool_calls") or []:
                if isinstance(call, dict) and call.get("id"):
                    function = call.get("function") or {}
                    calls[str(call["id"])] = (
                        str(function.get("name") or call.get("name") or "tool"),
                        _json_value(function.get("arguments", call.get("arguments"))),
                    )
            if str(message.get("role") or "").lower() != "tool":
                continue
            result = _message_content(message.get("content"))
            name, arguments = calls.get(
                str(message.get("tool_call_id") or ""), ("tool", None)
            )
            if not result or self._tool_result_recorded(name, result):
                continue
            self._ingest_tool_span(
                {
                    **span_dict,
                    "entity_type": "tool",
                    "entity_name": name,
                    "input_payload": arguments if isinstance(arguments, dict) else {},
                    "output_payload": {"output": _json_value(result)},
                },
                span_index,
                name,
            )

    def _tool_result_recorded(self, tool_name: str, result: str) -> bool:
        return any(
            fact.fact_type == "tool_output"
            and fact.source_name == tool_name
            and (
                result in fact.content
                or _safe_json(_json_value(result), max_len=None) in fact.content
            )
            for fact in self.evidence
        )

    def _ingest_llm_span(
        self, span_dict: Dict[str, Any], span_index: int, entity_name: str
    ) -> None:
        """Extract user messages as evidence and agent output as claims.

        Each LLM span's ``gen_ai.prompt.*`` contains the **full** accumulated
        chat history up to that point.  Without deduplication, the same user
        messages would be re-added as evidence on every LLM span, inflating
        context and distorting metric inputs.  We deduplicate by tracking the
        content of previously ingested user statements.
        """
        input_payload = span_dict.get("input_payload") or {}
        output_payload = span_dict.get("output_payload") or {}
        self._ingest_tool_exchanges(span_dict, span_index, input_payload)

        existing_user_texts = {
            f.content
            for f in self.evidence
            if f.fact_type
            in {
                "user_statement",
                "agent_handoff",
                "environment_context",
                "runtime_feedback",
            }
        }

        explicit_agent = self._explicit_agent_id(span_dict)
        if explicit_agent:
            self._observe_agent_span(span_dict, span_index, explicit_agent)
            # An allocator speaking again means its recipients handed back.
            self._close_returned_work(explicit_agent, span_index)
        work_unit = self._work_unit_for_span(span_dict, span_index, explicit_agent)
        if work_unit is not None:
            self._record_receipt(work_unit, span_index)
        delegated_task = (
            _is_delegated_agent_input(
                input_payload,
                root_policy_text=self.policy_text,
            )
            or work_unit is not None
        )
        agent_id = _span_agent_id(span_dict)
        provenance = self._operation_provenance(
            span_dict,
            delegated_task=delegated_task,
        )
        peer_assertion = delegated_task or provenance["actor_scope"] == "peer"
        if not peer_assertion and agent_id and not self.root_agent_id:
            self.root_agent_id = agent_id
        input_artifact_ids = self._input_artifact_ids(input_payload)
        # Only the work item this span executes under is a known link.
        related_intent_ids = (
            [work_unit.intent_id]
            if work_unit is not None and work_unit.intent_id
            else []
        )
        user_messages = _extract_user_messages(input_payload)
        embedded_user_requests = _ordered_union(
            [],
            [
                request
                for message in user_messages
                if (request := _extract_embedded_user_request(message))
            ],
        )
        if self.root_request and not embedded_user_requests:
            root = " ".join(self.root_request.split()).casefold()
            if any(
                root in (normalized := " ".join(message.split()).casefold())
                and len(normalized) > len(root) + 40
                for message in user_messages
            ):
                # An orchestration prompt that wraps the user's request in
                # instructions and replayed turns: only the request is theirs.
                embedded_user_requests = [self.root_request]
        message_records = [
            (request, "user_statement") for request in embedded_user_requests
        ]
        for message in user_messages:
            if _is_runtime_feedback_message(message):
                fact_type = "runtime_feedback"
            elif delegated_task or _is_coordination_context_message(message):
                fact_type = "agent_handoff"
            elif embedded_user_requests:
                fact_type = "environment_context"
            else:
                fact_type = "user_statement"
            message_records.append((message, fact_type))

        for msg, fact_type in message_records:
            contract_id, text = self._split_contract_prefix(msg)
            if contract_id:
                # An agent's instructions sent as a user-role message are its
                # contract, not a user request; keep only what follows them.
                input_artifact_ids.append(contract_id)
            text = text.strip()
            if text and text not in existing_user_texts:
                existing_user_texts.add(text)
                message_intent_ids = (
                    list(related_intent_ids) if fact_type == "agent_handoff" else []
                )
                fact_id = self._append_evidence(
                    EvidenceFact(
                        span_index=span_index,
                        fact_type=fact_type,
                        content=text,
                        source_name=(
                            "coordination_context"
                            if fact_type == "agent_handoff"
                            else fact_type.removesuffix("_statement")
                        ),
                        related_intent_ids=message_intent_ids,
                        **provenance,
                    )
                )
                input_artifact_ids.append(fact_id)
                self._link_artifacts_to_intents(
                    [fact_id],
                    message_intent_ids,
                    span_dict=span_dict,
                    span_index=span_index,
                )

        agent_text = _extract_agent_output(output_payload)
        output_artifact_ids: List[str] = []
        requested_tools = _requested_tool_names(output_payload)
        if explicit_agent:
            for tool_name in requested_tools:
                self._pending_tool_requesters[tool_name] = explicit_agent
            for tool_call_id in _requested_tool_call_ids(output_payload):
                self._tool_call_requesters[tool_call_id] = explicit_agent
        message_targets = self._message_targets(
            agent_text,
            output_payload,
            explicit_agent or agent_id,
        )
        # A turn that calls tools or messages another agent is still working:
        # it is neither a final answer nor evidence that intents are met.
        routing_output = (
            bool(message_targets)
            or bool(requested_tools)
            or _is_tool_call_only(agent_text)
        )
        if agent_text:
            if (
                not peer_assertion
                and not routing_output
                and _has_visible_content(agent_text)
            ):
                self.latest_root_answer = agent_text
                self.latest_root_answer_span_index = span_index
            linked_artifact_ids = self._linked_span_artifact_ids(span_dict)
            evidence_refs = _ordered_union(input_artifact_ids, linked_artifact_ids)
            round_index = _span_round_index(span_dict)
            phase = _span_phase(span_dict)
            previous_claim_id = self._latest_claim_by_agent.get(
                _normalise_actor_id(provenance["agent_id"]),
                "",
            )
            revision_of = ""
            if previous_claim_id and _is_revision_span(span_dict):
                revision_of = previous_claim_id
            claim_id = self._append_claim(
                ClaimEntry(
                    span_index=span_index,
                    claim_type=(
                        "peer_agent_assertion" if peer_assertion else "assertion"
                    ),
                    content=agent_text,
                    entity_name=entity_name,
                    related_intent_ids=related_intent_ids,
                    evidence_refs=evidence_refs,
                    revision_of_claim_id=revision_of,
                    phase=phase,
                    round_index=round_index,
                    work_id=work_unit.work_id if work_unit is not None else "",
                    **provenance,
                )
            )
            output_artifact_ids.append(claim_id)
            own_words = _reply_without_tool_calls(agent_text)
            if own_words and not message_targets:
                self._record_flags(
                    own_words,
                    span_index=span_index,
                    agent_id=provenance["agent_id"],
                    artifact_id=claim_id,
                    work_id=work_unit.work_id if work_unit is not None else "",
                )
            if provenance["agent_id"]:
                self._latest_claim_by_agent[
                    _normalise_actor_id(provenance["agent_id"])
                ] = claim_id
            for source_id in evidence_refs:
                self._add_provenance_link(
                    source_id,
                    claim_id,
                    "informs",
                    span_dict=span_dict,
                    span_index=span_index,
                )
            if revision_of:
                self._add_provenance_link(
                    revision_of,
                    claim_id,
                    "revised_by",
                    span_dict=span_dict,
                    span_index=span_index,
                )
            self._link_artifacts_to_intents(
                [claim_id],
                related_intent_ids,
                span_dict=span_dict,
                span_index=span_index,
            )
            self._observe_intent_ownership(
                related_intent_ids,
                provenance["agent_id"],
                provenance["actor_scope"],
                span_dict,
                span_index,
                basis=(
                    "delegated_execution"
                    if work_unit is not None
                    else "produced_output"
                ),
            )

        self._remember_span(
            span_dict,
            *input_artifact_ids,
            *output_artifact_ids,
        )
        if explicit_agent:
            self._latest_llm_agent_id = explicit_agent
        self._ingest_coordination_span(
            span_dict,
            span_index,
            input_artifact_ids=input_artifact_ids,
            output_artifact_ids=output_artifact_ids,
            related_intent_ids=related_intent_ids,
            additional_event_types=["assignment"] if message_targets else None,
            recipient_override=(
                [recipient for recipient, _ in message_targets]
                if message_targets
                else None
            ),
            request_override=(
                "\n".join(message for _, message in message_targets if message)
                if message_targets
                else ""
            ),
            source_override="message" if message_targets else "",
        )

    def _operation_provenance(
        self,
        span_dict: Dict[str, Any],
        *,
        delegated_task: Optional[bool] = None,
    ) -> Dict[str, str]:
        """Retain the actor and trace linkage needed by trajectory metrics."""
        agent_id = _span_agent_id(span_dict)
        explicit_scope = (
            str(span_dict.get("actor_scope") or _span_actor_scope(span_dict))
            .strip()
            .lower()
        )
        if explicit_scope in {"root", "peer"}:
            actor_scope = explicit_scope
        elif delegated_task is True:
            actor_scope = "peer"
        elif delegated_task is False:
            actor_scope = "root"
        elif agent_id and self.root_agent_id:
            actor_scope = (
                "root"
                if _normalise_actor_id(agent_id)
                == _normalise_actor_id(self.root_agent_id)
                else "peer"
            )
        else:
            actor_scope = ""
        return {
            "agent_id": agent_id,
            "actor_scope": actor_scope,
            "span_id": str(span_dict.get("span_id") or ""),
            "parent_span_id": str(span_dict.get("parent_span_id") or ""),
            "trace_id": str(span_dict.get("trace_id") or ""),
        }

    def _append_evidence(self, fact: EvidenceFact) -> str:
        index = len(self.evidence)
        self.evidence.append(fact)
        return self._evidence_artifact_id(index, fact)

    def _evidence_artifact_id(self, index: int, fact: EvidenceFact) -> str:
        if fact.fact_type == "user_statement":
            return f"user:{index}"
        if fact.fact_type == "policy_rule":
            if fact.source_name.startswith("semantic_contract:"):
                return fact.source_name
            if fact.source_name == "policy":
                return "policy:root"
        return f"fact:{index}"

    def _append_claim(self, claim: ClaimEntry) -> str:
        artifact_id = f"claim:{len(self.claims)}"
        self.claims.append(claim)
        return artifact_id

    def _remember_span(self, span_dict: Dict[str, Any], *artifact_ids: str) -> None:
        span_id = str(span_dict.get("span_id") or "")
        if not span_id:
            return
        stored = self._span_artifact_ids.setdefault(span_id, [])
        for artifact_id in artifact_ids:
            if artifact_id and artifact_id not in stored:
                stored.append(artifact_id)
        agent_id = _span_agent_id(span_dict)
        if agent_id:
            self._span_agent_ids[span_id] = agent_id

    def _linked_span_artifact_ids(self, span_dict: Dict[str, Any]) -> List[str]:
        artifact_ids: List[str] = []
        for link in _span_links(span_dict):
            artifact_ids = _ordered_union(
                artifact_ids,
                self._span_artifact_ids.get(link["span_id"], []),
            )
        return artifact_ids

    def _input_artifact_ids(self, input_payload: Dict[str, Any]) -> List[str]:
        """Resolve recorded prompt messages to artifacts already in context.

        A message links to an artifact only when the whole text is equal.
        """
        artifact_ids: List[str] = []
        for message in _extract_prompt_messages(input_payload):
            content = _exact_text_key(message["content"])
            role = message["role"]
            if role == "system":
                candidates = [
                    (self._evidence_artifact_id(index, fact), fact.content)
                    for index, fact in enumerate(self.evidence)
                    if fact.fact_type == "policy_rule"
                ]
            elif role in {"assistant", "ai"}:
                candidates = [
                    (f"claim:{index}", _reply_without_tool_calls(claim.content))
                    for index, claim in enumerate(self.claims)
                ]
            elif role in {"tool", "function"}:
                # A tool fact is stored as its call followed by the returned
                # payload; a later prompt replays only that payload.
                candidates = [
                    (
                        self._evidence_artifact_id(index, fact),
                        fact.content.partition("\n  Returned: ")[2],
                    )
                    for index, fact in enumerate(self.evidence)
                    if fact.fact_type == "tool_output"
                ]
            else:
                candidates = [
                    (self._evidence_artifact_id(index, fact), fact.content)
                    for index, fact in enumerate(self.evidence)
                    if fact.fact_type
                    in {
                        "agent_handoff",
                        "environment_context",
                        "runtime_feedback",
                        "user_statement",
                    }
                ]
            for artifact_id, candidate_content in candidates:
                if content and content == _exact_text_key(candidate_content):
                    artifact_ids.append(artifact_id)
        return _ordered_union([], artifact_ids)

    def _add_provenance_link(
        self,
        source_artifact_id: str,
        target_artifact_id: str,
        relation_type: str,
        *,
        span_dict: Dict[str, Any],
        span_index: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not source_artifact_id or not target_artifact_id:
            return
        identity = (source_artifact_id, target_artifact_id, relation_type)
        if any(
            (
                item.source_artifact_id,
                item.target_artifact_id,
                item.relation_type,
            )
            == identity
            for item in self.provenance_links
        ):
            return
        self.provenance_links.append(
            ArtifactProvenanceLink(
                source_artifact_id=source_artifact_id,
                target_artifact_id=target_artifact_id,
                relation_type=relation_type,
                span_index=span_index,
                span_id=str(span_dict.get("span_id") or ""),
                trace_id=str(span_dict.get("trace_id") or ""),
                metadata=dict(metadata or {}),
            )
        )

    def _link_artifacts_to_intents(
        self,
        artifact_ids: List[str],
        intent_ids: List[str],
        *,
        span_dict: Dict[str, Any],
        span_index: int,
    ) -> None:
        for artifact_id in artifact_ids:
            for intent_id in intent_ids:
                self._add_provenance_link(
                    artifact_id,
                    intent_id,
                    "advances",
                    span_dict=span_dict,
                    span_index=span_index,
                )

    def _observe_intent_ownership(
        self,
        intent_ids: List[str],
        agent_id: str,
        actor_scope: str,
        span_dict: Dict[str, Any],
        span_index: int,
        *,
        basis: str = "produced_output",
    ) -> None:
        """Record who handled an intent and on what evidence.

        ``basis`` separates receiving a request (``received_request``) from
        producing output for it (``produced_output``) and executing delegated
        work (``delegated_execution``). Rules that ask whether anyone actually
        worked on a requirement should not count ``received_request``.
        """
        if not agent_id:
            return
        for intent_id in intent_ids:
            intent = self._intent_by_artifact_id(intent_id)
            if intent is None:
                continue
            if (
                intent.source == "agent_plan"
                and intent.assignment_mode == "dynamic"
                and intent.owner_agent_ids
                and agent_id not in intent.owner_agent_ids
            ):
                continue
            if (
                intent.source in {"user", "policy", "root", "root_user"}
                and actor_scope == "peer"
                and any(
                    candidate.source == "agent_plan"
                    and agent_id in candidate.owner_agent_ids
                    for candidate in self.intents
                )
            ):
                continue
            if agent_id not in intent.owner_agent_ids:
                intent.owner_agent_ids.append(agent_id)
            if not intent.assignment_mode:
                intent.assignment_mode = "self" if actor_scope == "root" else "observed"
            phase = _span_phase(span_dict)
            round_index = _span_round_index(span_dict)
            if phase:
                intent.phase = phase
            if round_index is not None:
                intent.round_index = round_index
            event = {
                "span_index": span_index,
                "type": "owner_observed",
                "agent_id": agent_id,
                "assignment_mode": intent.assignment_mode,
                "basis": basis,
            }
            if round_index is not None:
                event["round_index"] = round_index
            if phase:
                event["phase"] = phase
            existing = next(
                (
                    item
                    for item in intent.events
                    if item.get("type") == "owner_observed"
                    and item.get("agent_id") == agent_id
                ),
                None,
            )
            if existing is None:
                event["bases"] = [basis]
                intent.events.append(event)
            else:
                bases = existing.setdefault("bases", [existing.get("basis", basis)])
                if basis not in bases:
                    bases.append(basis)

    def _intent_by_artifact_id(self, artifact_id: str) -> Optional[IntentEntry]:
        match = re.fullmatch(r"intent:(\d+)", artifact_id)
        if not match:
            return None
        index = int(match.group(1))
        return self.intents[index] if index < len(self.intents) else None

    def _ingest_coordination_span(
        self,
        span_dict: Dict[str, Any],
        span_index: int,
        *,
        input_artifact_ids: Optional[List[str]] = None,
        output_artifact_ids: Optional[List[str]] = None,
        related_intent_ids: Optional[List[str]] = None,
        additional_event_types: Optional[List[str]] = None,
        recipient_override: Optional[List[str]] = None,
        actor_override: str = "",
        suppressed_event_types: Optional[set[str]] = None,
        request_override: str = "",
        only_event_types: Optional[set[str]] = None,
        source_override: str = "",
    ) -> None:
        """Normalize coordination semantics without branching on topology."""
        self._update_coordination_metadata(span_dict)
        links = _span_links(span_dict)
        event_types = _coordination_event_types(span_dict, links)
        event_types = _ordered_union(event_types, additional_event_types or [])
        event_types = [
            event_type
            for event_type in event_types
            if event_type not in (suppressed_event_types or set())
            and (only_event_types is None or event_type in only_event_types)
        ]
        if not event_types:
            return

        parent_span_id = str(span_dict.get("parent_span_id") or "")
        parent_types = self._span_coordination_event_types.get(parent_span_id, set())

        actor_agent_id = actor_override or _span_agent_id(span_dict)
        linked_span_ids = [link["span_id"] for link in links if link["span_id"]]
        link_types = _ordered_union([], [link["link_type"] for link in links])
        sender_agent_ids = _ordered_union(
            [],
            [
                self._span_agent_ids.get(linked_span_id, "")
                for linked_span_id in linked_span_ids
            ],
        )
        sender_agent_ids = [item for item in sender_agent_ids if item]
        span_recipient_ids = _span_recipient_agent_ids(span_dict)
        if not span_recipient_ids and any(
            event_type in {"assignment", "handoff"} for event_type in event_types
        ):
            span_recipient_ids = _infer_operation_recipient_agent_ids(span_dict)
        if self._roster_complete:
            declared_targets = _declared_recipient_ids(span_dict)
            kept: List[str] = []
            for recipient in span_recipient_ids:
                known = self._known_agent_id(recipient)
                if not known and recipient in declared_targets:
                    # Named by a delegation attribute or operation: an agent
                    # even if it never runs, which is how a role gap looks.
                    profile = self.declare_agent(
                        recipient,
                        span_index=span_index,
                        declared_by="delegation_target",
                    )
                    known = profile.agent_id if profile is not None else ""
                if known:
                    kept.append(known)
            span_recipient_ids = _ordered_union([], kept)
        recipient_agent_ids = (
            list(recipient_override)
            if recipient_override is not None
            else span_recipient_ids
        )

        operation = _normalise_operation_text(span_dict)
        link_handoff = (
            "handoff" in event_types
            and not re.search(
                r"\b(?:delegat|handoff|hand_off|return_to|transfer)\w*\b", operation
            )
            and not span_recipient_ids
        )
        handoff_recipient_ids: List[str] = []
        handoff_sender_ids: List[str] = []
        if link_handoff:
            # A typed handoff link on a span means work arrived at the span's
            # agent from the linked sender; a self-link is a continuation.
            receiver = self._explicit_agent_id(span_dict)
            if self._roster_complete:
                receiver = self._known_agent_id(receiver)
            link_senders = _ordered_union(
                [],
                [
                    self._known_agent_id(link.get("from_agent", ""))
                    or link["from_agent"]
                    for link in links
                    if link.get("from_agent")
                ],
            )
            senders = link_senders or sender_agent_ids
            if (
                receiver
                and senders
                and all(
                    _normalise_actor_id(sender) != _normalise_actor_id(receiver)
                    for sender in senders
                )
            ):
                handoff_recipient_ids = [receiver]
                handoff_sender_ids = senders
                if recipient_override is None:
                    recipient_agent_ids = [receiver]
                    sender_agent_ids = senders
            else:
                link_handoff = False
                event_types = [item for item in event_types if item != "handoff"]

        def recipients_for(event_type: str) -> List[str]:
            if event_type == "handoff" and link_handoff:
                return handoff_recipient_ids
            return recipient_agent_ids

        def senders_for(event_type: str) -> List[str]:
            if event_type == "handoff" and link_handoff:
                return handoff_sender_ids
            if event_type == "assignment" and actor_override:
                # A routed assignment is sent by its allocator, not by the
                # agent whose handoff link the same span carries.
                return [actor_agent_id] if actor_agent_id else []
            return sender_agent_ids

        if self._roster_complete:
            event_types = [
                item
                for item in event_types
                if item not in {"assignment", "handoff"} or recipients_for(item)
            ]
        if not event_types:
            return

        linked_artifact_ids = self._linked_span_artifact_ids(span_dict)
        referenced_claim_ids = self._referenced_agent_claim_ids(span_dict)
        input_ids = _ordered_union(input_artifact_ids or [], linked_artifact_ids)
        input_ids = _ordered_union(input_ids, referenced_claim_ids)
        output_ids = list(output_artifact_ids or [])
        intent_ids = list(related_intent_ids or [])

        duplicate_types = [
            event_type for event_type in event_types if event_type in parent_types
        ]
        for event_type in duplicate_types:
            self._merge_parent_coordination_event(
                parent_span_id,
                event_type,
                span_dict=span_dict,
                input_artifact_ids=input_ids,
                output_artifact_ids=output_ids,
                related_intent_ids=intent_ids,
                sender_agent_ids=senders_for(event_type),
                recipient_agent_ids=recipients_for(event_type),
                linked_span_ids=linked_span_ids,
                link_types=link_types,
            )
            event_types.remove(event_type)
        if not event_types:
            return

        span_id = str(span_dict.get("span_id") or "")
        if request_override or source_override == "message":
            request_text = request_override
        elif actor_override:
            # A router's input is the whole graph state; the allocator's own
            # latest turn is the decision that carries the request.
            request_text = self._latest_claim_text(
                actor_agent_id
            ) or _span_work_description(span_dict)
        else:
            request_text = _span_work_description(span_dict)
        source = source_override or (
            "route" if actor_override else ("message" if request_override else "span")
        )
        call_id = (
            _span_call_id(span_dict) if span_dict.get("entity_type") == "tool" else ""
        )
        span_unit: Optional[WorkUnit] = None
        for event_type in event_types:
            type_recipient_ids = recipients_for(event_type)
            type_sender_ids = senders_for(event_type)
            event_intent_ids = list(intent_ids)
            assignment_intent_ids: List[str] = []
            event_unit: Optional[WorkUnit] = None
            if event_type == "handoff" and link_handoff:
                event_unit = self._work_unit_for_span(
                    span_dict,
                    span_index,
                    type_recipient_ids[0] if type_recipient_ids else "",
                )
                if event_unit is not None and event_unit.intent_id:
                    assignment_intent_ids = [event_unit.intent_id]
                    event_intent_ids = _ordered_union(
                        assignment_intent_ids, event_intent_ids
                    )
            elif event_type in {"assignment", "handoff"}:
                assignment_intent_ids = self._ensure_assignment_intent(
                    span_dict,
                    span_index,
                    event_type=event_type,
                    parent_intent_ids=intent_ids,
                    recipient_agent_ids=type_recipient_ids,
                    description_override=request_text if actor_override else "",
                    actor_override=actor_override,
                )
                event_intent_ids = _ordered_union(
                    assignment_intent_ids,
                    [
                        parent_id
                        for intent_id in assignment_intent_ids
                        if (intent := self._intent_by_artifact_id(intent_id))
                        is not None
                        for parent_id in intent.parent_intent_ids
                    ],
                )
                if span_unit is None and (
                    event_type == "assignment" or "assignment" not in event_types
                ):
                    span_unit = self._open_work_unit(
                        allocator_agent_id=actor_agent_id,
                        recipient_agent_ids=type_recipient_ids,
                        request=request_text,
                        span_index=span_index,
                        source=source,
                        call_id=call_id,
                        source_span_ids=[span_id] if span_id else [],
                        intent_ids=assignment_intent_ids,
                    )
                event_unit = span_unit
            if event_type == "peer_message" and actor_agent_id:
                recipient_ids = [actor_agent_id]
            else:
                recipient_ids = list(type_recipient_ids)
            if event_type in {"assignment", "handoff"} and not type_sender_ids:
                event_senders = [actor_agent_id] if actor_agent_id else []
            else:
                event_senders = list(type_sender_ids)

            existing_event = self._coordination_event_for_span(
                event_type,
                span_id,
                linked_span_ids,
                recipient_agent_ids=recipient_ids,
            )
            if existing_event is not None:
                self._merge_coordination_event(
                    existing_event,
                    span_dict=span_dict,
                    span_index=span_index,
                    input_artifact_ids=input_ids,
                    output_artifact_ids=output_ids,
                    related_intent_ids=event_intent_ids,
                    assignment_intent_ids=assignment_intent_ids,
                    sender_agent_ids=event_senders,
                    recipient_agent_ids=recipient_ids,
                    linked_span_ids=linked_span_ids,
                    link_types=link_types,
                )
                if event_unit is None and existing_event.work_id:
                    event_unit = self._work_unit_by_id(existing_event.work_id)
                if event_unit is not None:
                    existing_event.work_id = (
                        existing_event.work_id or event_unit.work_id
                    )
                    if existing_event.event_id not in event_unit.assignment_event_ids:
                        event_unit.assignment_event_ids.append(existing_event.event_id)
                continue

            event_id = f"coordination:{len(self.coordination_events)}"
            event = CoordinationEvent(
                event_id=event_id,
                span_index=span_index,
                event_type=event_type,
                operation_name=str(span_dict.get("entity_name") or "unknown"),
                actor_agent_id=actor_agent_id,
                sender_agent_ids=event_senders,
                recipient_agent_ids=recipient_ids,
                related_intent_ids=event_intent_ids,
                input_artifact_ids=input_ids,
                output_artifact_ids=output_ids,
                linked_span_ids=linked_span_ids,
                link_types=link_types,
                assignment_mode=("dynamic" if event_type == "assignment" else ""),
                status=_coordination_event_status(span_dict, event_type),
                content=_coordination_content(span_dict),
                phase=_span_phase(span_dict),
                round_index=_span_round_index(span_dict),
                span_id=span_id,
                parent_span_id=parent_span_id,
                trace_id=str(span_dict.get("trace_id") or ""),
                work_id=event_unit.work_id if event_unit is not None else "",
            )
            self.coordination_events.append(event)
            if event_unit is not None:
                event_unit.assignment_event_ids.append(event_id)
            self._remember_span(span_dict, event_id)
            self._span_coordination_event_types.setdefault(
                event.span_id,
                set(),
            ).add(event_type)

            for source_id in input_ids:
                self._add_provenance_link(
                    source_id,
                    event_id,
                    "informs",
                    span_dict=span_dict,
                    span_index=span_index,
                    metadata={"link_types": link_types},
                )
            for target_id in output_ids:
                self._add_provenance_link(
                    event_id,
                    target_id,
                    "produces",
                    span_dict=span_dict,
                    span_index=span_index,
                )
            if event_unit is not None:
                self._add_provenance_link(
                    event_id,
                    event_unit.work_id,
                    "assigns" if event_type == "assignment" else "communicates",
                    span_dict=span_dict,
                    span_index=span_index,
                )
            self._link_artifacts_to_intents(
                [event_id],
                event_intent_ids,
                span_dict=span_dict,
                span_index=span_index,
            )
            self._record_coordination_on_intents(
                event,
                assignment_intent_ids=assignment_intent_ids,
            )

    def _latest_claim_text(self, agent_id: str) -> str:
        for claim in reversed(self.claims):
            if claim.agent_id == agent_id and claim.claim_type != "tool_result":
                return claim.content
        return ""

    def _coordination_event_for_span(
        self,
        event_type: str,
        span_id: str,
        linked_span_ids: List[str],
        *,
        recipient_agent_ids: Optional[List[str]] = None,
    ) -> Optional[CoordinationEvent]:
        source_span_ids = {span_id, *linked_span_ids} - {""}
        if not source_span_ids:
            return None
        wanted = set(recipient_agent_ids or [])
        for event in reversed(self.coordination_events):
            if event.event_type != event_type:
                continue
            if (
                wanted
                and event.recipient_agent_ids
                and (set(event.recipient_agent_ids) != wanted)
            ):
                # A different hop between other agents is not the same event.
                continue
            event_span_ids = {event.span_id, *event.linked_span_ids} - {""}
            if source_span_ids & event_span_ids:
                return event
        return None

    def _merge_coordination_event(
        self,
        event: CoordinationEvent,
        *,
        span_dict: Dict[str, Any],
        span_index: int,
        input_artifact_ids: List[str],
        output_artifact_ids: List[str],
        related_intent_ids: List[str],
        assignment_intent_ids: List[str],
        sender_agent_ids: List[str],
        recipient_agent_ids: List[str],
        linked_span_ids: List[str],
        link_types: List[str],
    ) -> None:
        """Enrich an adapter event with canonical span artifacts and provenance."""
        new_intent_ids = [
            intent_id
            for intent_id in related_intent_ids
            if intent_id not in event.related_intent_ids
        ]
        event.span_index = span_index
        event.operation_name = str(
            span_dict.get("entity_name") or event.operation_name or "unknown"
        )
        event.actor_agent_id = _span_agent_id(span_dict) or event.actor_agent_id
        event.sender_agent_ids = _ordered_union(
            event.sender_agent_ids,
            sender_agent_ids,
        )
        event.recipient_agent_ids = _ordered_union(
            event.recipient_agent_ids,
            recipient_agent_ids,
        )
        event.related_intent_ids = _ordered_union(
            event.related_intent_ids,
            related_intent_ids,
        )
        event.input_artifact_ids = _ordered_union(
            event.input_artifact_ids,
            input_artifact_ids,
        )
        event.output_artifact_ids = _ordered_union(
            event.output_artifact_ids,
            output_artifact_ids,
        )
        event.linked_span_ids = _ordered_union(
            event.linked_span_ids,
            linked_span_ids,
        )
        event.link_types = _ordered_union(event.link_types, link_types)
        event.status = _coordination_event_status(span_dict, event.event_type)
        canonical_content = _coordination_content(span_dict)
        if canonical_content:
            event.content = canonical_content
        event.phase = _span_phase(span_dict) or event.phase
        event.round_index = _span_round_index(span_dict) or event.round_index
        event.span_id = str(span_dict.get("span_id") or event.span_id)
        event.parent_span_id = str(
            span_dict.get("parent_span_id") or event.parent_span_id
        )
        event.trace_id = str(span_dict.get("trace_id") or event.trace_id)

        self._remember_span(span_dict, event.event_id)
        if event.span_id:
            self._span_coordination_event_types.setdefault(
                event.span_id,
                set(),
            ).add(event.event_type)
        for source_id in input_artifact_ids:
            self._add_provenance_link(
                source_id,
                event.event_id,
                "informs",
                span_dict=span_dict,
                span_index=span_index,
                metadata={"link_types": link_types},
            )
        for target_id in output_artifact_ids:
            self._add_provenance_link(
                event.event_id,
                target_id,
                "produces",
                span_dict=span_dict,
                span_index=span_index,
            )
        self._link_artifacts_to_intents(
            [event.event_id],
            new_intent_ids,
            span_dict=span_dict,
            span_index=span_index,
        )
        if new_intent_ids:
            original_intent_ids = event.related_intent_ids
            event.related_intent_ids = new_intent_ids
            self._record_coordination_on_intents(
                event,
                assignment_intent_ids=assignment_intent_ids,
            )
            event.related_intent_ids = original_intent_ids

    def _ensure_assignment_intent(
        self,
        span_dict: Dict[str, Any],
        span_index: int,
        *,
        event_type: str,
        parent_intent_ids: List[str],
        recipient_agent_ids: List[str],
        description_override: str = "",
        actor_override: str = "",
    ) -> List[str]:
        """Create one child work item for an explicit assignment or handoff."""
        description = description_override or _span_work_description(span_dict)
        if not description and event_type == "handoff":
            return []
        if not description and recipient_agent_ids:
            description = f"Work assigned to {', '.join(recipient_agent_ids)}"
        if not description:
            return []

        span_id = str(span_dict.get("span_id") or "")
        for index, intent in enumerate(self.intents):
            if intent.source != "agent_plan":
                continue
            same_span = any(
                event.get("span_id") == span_id
                and event.get("type") in {"assignment", "handoff"}
                for event in intent.events
            )
            same_work = _normalise_semantic_text(intent.description) == (
                _normalise_semantic_text(description)
            ) and bool(set(intent.owner_agent_ids) & set(recipient_agent_ids))
            if same_span or same_work:
                intent.parent_intent_ids = _ordered_union(
                    intent.parent_intent_ids,
                    parent_intent_ids,
                )
                intent.dependency_intent_ids = _ordered_union(
                    intent.dependency_intent_ids,
                    self._resolve_intent_references(
                        _span_intent_references(span_dict, dependency=True)
                    ),
                )
                return [f"intent:{index}"]

        actor_agent_id = actor_override or _span_agent_id(span_dict)
        expected_output = _span_expected_output_from_payload(span_dict)
        dependency_intent_ids = self._resolve_intent_references(
            _span_intent_references(span_dict, dependency=True)
        )
        explicit_parent_ids = self._resolve_intent_references(
            _span_intent_references(span_dict, dependency=False)
        )
        inferred_root_ids = [
            intent_id
            for intent_id in parent_intent_ids
            if (intent := self._intent_by_artifact_id(intent_id)) is not None
            and intent.source != "agent_plan"
        ]
        if not inferred_root_ids:
            inferred_root_ids = [
                f"intent:{index}"
                for index, intent in enumerate(self.intents)
                if intent.source in {"user", "policy", "root", "root_user"}
            ][:4]
        resolved_parent_ids = _ordered_union(explicit_parent_ids, inferred_root_ids)
        recipient_name = "_and_".join(
            _normalise_actor_id(agent_id) for agent_id in recipient_agent_ids
        ).strip("_")
        base_name = f"delegated_{recipient_name or 'work'}"
        intent = IntentEntry(
            name=_unique_intent_name(
                base_name,
                {existing.name for existing in self.intents},
            ),
            description=description,
            requirement_type="subtask",
            source="agent_plan",
            first_seen=span_index,
            last_seen=span_index,
            status="in_progress",
            events=[
                {
                    "span_index": span_index,
                    "span_id": span_id,
                    "type": event_type,
                    "actor_agent_id": actor_agent_id,
                    "recipient_agent_ids": list(recipient_agent_ids),
                }
            ],
            owner_agent_ids=list(recipient_agent_ids),
            assigned_by_agent_id=actor_agent_id,
            assignment_mode="dynamic",
            parent_intent_ids=resolved_parent_ids,
            dependency_intent_ids=dependency_intent_ids,
            expected_output=expected_output,
            phase=_span_phase(span_dict),
            round_index=_span_round_index(span_dict),
        )
        self.intents.append(intent)
        intent_id = f"intent:{len(self.intents) - 1}"
        for parent_id in resolved_parent_ids:
            self._add_provenance_link(
                parent_id,
                intent_id,
                "decomposes_to",
                span_dict=span_dict,
                span_index=span_index,
            )
        for dependency_id in dependency_intent_ids:
            self._add_provenance_link(
                dependency_id,
                intent_id,
                "precedes",
                span_dict=span_dict,
                span_index=span_index,
            )
        return [intent_id]

    def _resolve_intent_references(self, references: List[str]) -> List[str]:
        resolved: List[str] = []
        for reference in references:
            if re.fullmatch(r"intent:\d+", reference) and self._intent_by_artifact_id(
                reference
            ):
                resolved.append(reference)
                continue
            normalized = _normalise_semantic_text(reference)
            exact = next(
                (
                    f"intent:{index}"
                    for index, intent in enumerate(self.intents)
                    if normalized
                    in {
                        _normalise_semantic_text(intent.name),
                        _normalise_semantic_text(intent.description),
                    }
                ),
                "",
            )
            if exact:
                resolved.append(exact)
        return _ordered_union([], resolved)

    def _merge_parent_coordination_event(
        self,
        parent_span_id: str,
        event_type: str,
        *,
        span_dict: Dict[str, Any],
        input_artifact_ids: List[str],
        output_artifact_ids: List[str],
        related_intent_ids: List[str],
        sender_agent_ids: List[str],
        recipient_agent_ids: List[str],
        linked_span_ids: List[str],
        link_types: List[str],
    ) -> None:
        parent_event = next(
            (
                event
                for event in reversed(self.coordination_events)
                if event.span_id == parent_span_id and event.event_type == event_type
            ),
            None,
        )
        if parent_event is None:
            return

        new_intent_ids = [
            intent_id
            for intent_id in related_intent_ids
            if intent_id not in parent_event.related_intent_ids
        ]
        parent_event.input_artifact_ids = _ordered_union(
            parent_event.input_artifact_ids,
            input_artifact_ids,
        )
        parent_event.output_artifact_ids = _ordered_union(
            parent_event.output_artifact_ids,
            output_artifact_ids,
        )
        parent_event.related_intent_ids = _ordered_union(
            parent_event.related_intent_ids,
            related_intent_ids,
        )
        parent_event.sender_agent_ids = _ordered_union(
            parent_event.sender_agent_ids,
            sender_agent_ids,
        )
        parent_event.recipient_agent_ids = _ordered_union(
            parent_event.recipient_agent_ids,
            recipient_agent_ids,
        )
        parent_event.linked_span_ids = _ordered_union(
            parent_event.linked_span_ids,
            linked_span_ids,
        )
        parent_event.link_types = _ordered_union(
            parent_event.link_types,
            link_types,
        )
        child_content = _coordination_content(span_dict)
        if child_content:
            parent_event.content = child_content
        parent_event.status = _span_operation_status(span_dict)

        self._remember_span(span_dict, parent_event.event_id)
        child_span_id = str(span_dict.get("span_id") or "")
        self._span_coordination_event_types.setdefault(child_span_id, set()).add(
            event_type
        )
        for source_id in input_artifact_ids:
            self._add_provenance_link(
                source_id,
                parent_event.event_id,
                "informs",
                span_dict=span_dict,
                span_index=parent_event.span_index,
                metadata={"link_types": link_types},
            )
        for target_id in output_artifact_ids:
            self._add_provenance_link(
                parent_event.event_id,
                target_id,
                "produces",
                span_dict=span_dict,
                span_index=parent_event.span_index,
            )
        self._link_artifacts_to_intents(
            [parent_event.event_id],
            new_intent_ids,
            span_dict=span_dict,
            span_index=parent_event.span_index,
        )
        if new_intent_ids:
            original_intent_ids = parent_event.related_intent_ids
            parent_event.related_intent_ids = new_intent_ids
            self._record_coordination_on_intents(parent_event)
            parent_event.related_intent_ids = original_intent_ids

    def _referenced_agent_claim_ids(
        self,
        span_dict: Dict[str, Any],
    ) -> List[str]:
        claim_ids: List[str] = []
        for agent_id in _payload_agent_references(span_dict.get("input_payload")):
            claim_id = self._latest_claim_by_agent.get(
                _normalise_actor_id(agent_id),
                "",
            )
            if claim_id:
                claim_ids.append(claim_id)
        return _ordered_union([], claim_ids)

    def _record_coordination_on_intents(
        self,
        event: CoordinationEvent,
        *,
        assignment_intent_ids: Optional[List[str]] = None,
    ) -> None:
        assigned_ids = set(assignment_intent_ids or [])
        for intent_id in event.related_intent_ids:
            intent = self._intent_by_artifact_id(intent_id)
            if intent is None:
                continue
            intent.last_seen = max(intent.last_seen, event.span_index)
            if event.event_type == "assignment" and intent_id in assigned_ids:
                is_child_work = intent.source == "agent_plan"
                if is_child_work:
                    for recipient in event.recipient_agent_ids:
                        if recipient and recipient not in intent.owner_agent_ids:
                            intent.owner_agent_ids.append(recipient)
                    intent.assigned_by_agent_id = event.actor_agent_id
                    intent.assignment_mode = "dynamic"
                    expected_output = _span_expected_output(event.content)
                    if expected_output:
                        intent.expected_output = expected_output
            if event.phase:
                intent.phase = event.phase
            if event.round_index is not None:
                intent.round_index = event.round_index
            intent.events.append(
                {
                    "span_index": event.span_index,
                    "type": event.event_type,
                    "event_id": event.event_id,
                    "actor_agent_id": event.actor_agent_id,
                    "sender_agent_ids": event.sender_agent_ids,
                    "recipient_agent_ids": event.recipient_agent_ids,
                    "round_index": event.round_index,
                    "phase": event.phase,
                }
            )

    def _record_final_synthesis(self, text: str, span_index: int) -> None:
        existing = next(
            (
                event
                for event in reversed(self.coordination_events)
                if event.event_type == "synthesis"
                and (
                    event.span_index == span_index
                    or _normalise_semantic_text(event.content)
                    == _normalise_semantic_text(text)
                )
            ),
            None,
        )
        claim_index = next(
            (
                index
                for index in range(len(self.claims) - 1, -1, -1)
                if self.claims[index].span_index == span_index
            ),
            None,
        )
        claim = self.claims[claim_index] if claim_index is not None else None
        span_dict: Dict[str, Any] = {
            "span_id": claim.span_id if claim else "",
            "parent_span_id": claim.parent_span_id if claim else "",
            "trace_id": claim.trace_id if claim else "",
            "agent_id": claim.agent_id if claim else "",
        }

        if existing is not None:
            existing.span_index = span_index
            existing.content = text
            if claim is not None:
                existing.operation_name = claim.entity_name or existing.operation_name
                existing.actor_agent_id = claim.agent_id or existing.actor_agent_id
                existing.related_intent_ids = _ordered_union(
                    existing.related_intent_ids,
                    claim.related_intent_ids,
                )
                existing.input_artifact_ids = _ordered_union(
                    existing.input_artifact_ids,
                    claim.evidence_refs,
                )
                existing.phase = claim.phase or existing.phase
                existing.round_index = claim.round_index or existing.round_index
                existing.span_id = claim.span_id or existing.span_id
                existing.parent_span_id = (
                    claim.parent_span_id or existing.parent_span_id
                )
                existing.trace_id = claim.trace_id or existing.trace_id
            if "final_answer" not in existing.output_artifact_ids:
                existing.output_artifact_ids.append("final_answer")
            self._remember_span(span_dict, existing.event_id)
            for source_id in existing.input_artifact_ids:
                self._add_provenance_link(
                    source_id,
                    existing.event_id,
                    "informs",
                    span_dict=span_dict,
                    span_index=span_index,
                )
            self._add_provenance_link(
                existing.event_id,
                "final_answer",
                "produces",
                span_dict=span_dict,
                span_index=span_index,
            )
            return

        input_artifact_ids = list(claim.evidence_refs) if claim else []
        related_intent_ids = list(claim.related_intent_ids) if claim else []
        event = CoordinationEvent(
            event_id=f"coordination:{len(self.coordination_events)}",
            span_index=span_index,
            event_type="synthesis",
            operation_name=claim.entity_name if claim else "final_synthesis",
            actor_agent_id=claim.agent_id if claim else "",
            related_intent_ids=related_intent_ids,
            input_artifact_ids=input_artifact_ids,
            output_artifact_ids=["final_answer"],
            status="observed",
            content=text,
            phase=claim.phase if claim else "",
            round_index=claim.round_index if claim else None,
            span_id=claim.span_id if claim else "",
            parent_span_id=claim.parent_span_id if claim else "",
            trace_id=claim.trace_id if claim else "",
        )
        self.coordination_events.append(event)
        self._remember_span(span_dict, event.event_id)
        if event.span_id:
            self._span_coordination_event_types.setdefault(
                event.span_id,
                set(),
            ).add("synthesis")
        for source_id in input_artifact_ids:
            self._add_provenance_link(
                source_id,
                event.event_id,
                "informs",
                span_dict=span_dict,
                span_index=span_index,
            )
        self._add_provenance_link(
            event.event_id,
            "final_answer",
            "produces",
            span_dict=span_dict,
            span_index=span_index,
        )
        self._link_artifacts_to_intents(
            [event.event_id],
            related_intent_ids,
            span_dict=span_dict,
            span_index=span_index,
        )
        self._record_coordination_on_intents(event)

    def _update_coordination_metadata(self, span_dict: Dict[str, Any]) -> None:
        attrs = _span_attributes(span_dict)
        topology = _first_populated(
            attrs,
            "mas.communication.topology",
            "coordination.topology",
        )
        architecture = _first_populated(
            attrs,
            "mas.architecture",
            "coordination.architecture",
        )
        if topology and not self.coordination_metadata.get("topology"):
            self.coordination_metadata["topology"] = topology
        if architecture and not self.coordination_metadata.get("architecture"):
            self.coordination_metadata["architecture"] = architecture

        agent_id = _span_agent_id(span_dict)
        if self._roster_complete:
            # With a declared roster, an app or service name is not an agent.
            agent_id = self._known_agent_id(agent_id)
        if not agent_id:
            return
        agents = self.coordination_metadata.setdefault("agents", {})
        agent = agents.setdefault(agent_id, {})
        for target, keys in (
            ("role", ("mas.agent.role", "agent.role")),
            ("objective", ("mas.agent.objective", "agent.objective")),
            ("capabilities", ("mas.agent.capabilities", "agent.capabilities")),
        ):
            value = _first_populated(attrs, *keys)
            if value not in (None, "") and target not in agent:
                agent[target] = _json_value(value)

    def rebuild_runtime_indexes(self) -> None:
        """Rebuild private lookup indexes after loading a persisted context."""
        self.root_agent_id = ""
        self._span_artifact_ids = {}
        self._span_agent_ids = {}
        self._span_coordination_event_types = {}
        self._latest_claim_by_agent = {}
        for index, fact in enumerate(self.evidence):
            if fact.span_id:
                self._span_artifact_ids.setdefault(fact.span_id, []).append(
                    self._evidence_artifact_id(index, fact)
                )
                if fact.agent_id:
                    self._span_agent_ids[fact.span_id] = fact.agent_id
        for index, claim in enumerate(self.claims):
            claim_id = f"claim:{index}"
            if (
                not self.root_agent_id
                and claim.agent_id
                and claim.actor_scope == "root"
            ):
                self.root_agent_id = claim.agent_id
            if claim.span_id:
                self._span_artifact_ids.setdefault(claim.span_id, []).append(claim_id)
                if claim.agent_id:
                    self._span_agent_ids[claim.span_id] = claim.agent_id
            if claim.agent_id:
                self._latest_claim_by_agent[_normalise_actor_id(claim.agent_id)] = (
                    claim_id
                )
        for event in self.coordination_events:
            if not event.span_id:
                continue
            self._span_artifact_ids.setdefault(event.span_id, []).append(event.event_id)
            if event.actor_agent_id:
                self._span_agent_ids[event.span_id] = event.actor_agent_id
            self._span_coordination_event_types.setdefault(event.span_id, set()).add(
                event.event_type
            )

    # ------------------------------------------------------------------
    # Retrieval: tailored context for each metric
    # ------------------------------------------------------------------

    def retrieve_for_state_delta(
        self,
        current_span: Dict[str, Any],
        *,
        max_facts: int = 12,
        max_claims: int = 10,
        max_item_chars: int = 1200,
    ) -> Dict[str, Any]:
        """Return one compact, deduplicated state view for all span primitives.

        The old span path rendered three separate strings and repeated policy,
        evidence, and reasoning history for Groundedness, Intent Recognition,
        and Relevancy.  This representation is deliberately policy-free (the
        caller sends policy once) and contains only the state needed to judge
        the current transition.  ``current_span`` is kept for API
        compatibility; selection is by recency, not by the span's text.
        """
        current_index = self._current_span_index()
        recent_evidence = self._get_recent_evidence(current_index)
        selected: List[EvidenceFact] = list(recent_evidence)
        selected_keys = {
            (item.span_index, item.fact_type, item.source_name, item.content)
            for item in selected
        }

        # Fill the remaining slots with the most recent other facts.
        older = [
            fact
            for fact in self.evidence
            if (
                fact.span_index,
                fact.fact_type,
                fact.source_name,
                fact.content,
            )
            not in selected_keys
        ]
        for fact in sorted(older, key=lambda item: item.span_index, reverse=True):
            if len(selected) >= max_facts:
                break
            selected.append(fact)

        return {
            "intents": [
                {
                    "name": intent.name,
                    "description": intent.description[:max_item_chars],
                    "requirement_type": intent.requirement_type,
                    "source": intent.source,
                    "status": intent.status,
                    "first_seen": intent.first_seen,
                    "last_seen": intent.last_seen,
                    "owner_agent_ids": intent.owner_agent_ids,
                    "assigned_by_agent_id": intent.assigned_by_agent_id,
                    "assignment_mode": intent.assignment_mode,
                    "dependency_intent_ids": intent.dependency_intent_ids,
                    "expected_output": intent.expected_output[:max_item_chars],
                    "phase": intent.phase,
                    "round_index": intent.round_index,
                    "recent_events": intent.events[-3:],
                }
                for intent in self.intents
                if intent.source != "agent_plan"
            ],
            "facts": [
                {
                    "span_index": fact.span_index,
                    "fact_type": fact.fact_type,
                    "source_name": fact.source_name,
                    "agent_id": fact.agent_id,
                    "span_id": fact.span_id,
                    "related_intent_ids": fact.related_intent_ids,
                    "content": fact.content[:max_item_chars],
                }
                for fact in selected[:max_facts]
            ],
            "recent_claims": [
                {
                    "span_index": claim.span_index,
                    "claim_type": claim.claim_type,
                    "entity_name": claim.entity_name,
                    "agent_id": claim.agent_id,
                    "span_id": claim.span_id,
                    "related_intent_ids": claim.related_intent_ids,
                    "evidence_refs": claim.evidence_refs,
                    "revision_of_claim_id": claim.revision_of_claim_id,
                    "phase": claim.phase,
                    "round_index": claim.round_index,
                    "content": claim.content[:max_item_chars],
                }
                for claim in self.claims[-max_claims:]
            ],
            "recent_coordination_events": [
                {
                    "event_id": event.event_id,
                    "span_index": event.span_index,
                    "event_type": event.event_type,
                    "operation_name": event.operation_name,
                    "actor_agent_id": event.actor_agent_id,
                    "sender_agent_ids": event.sender_agent_ids,
                    "recipient_agent_ids": event.recipient_agent_ids,
                    "related_intent_ids": event.related_intent_ids,
                    "input_artifact_ids": event.input_artifact_ids,
                    "output_artifact_ids": event.output_artifact_ids,
                    "phase": event.phase,
                    "round_index": event.round_index,
                }
                for event in self.coordination_events[-10:]
            ],
        }

    def retrieve_for_intent_recognition(
        self, current_span: Dict[str, Any], *, budget: Optional[int] = None
    ) -> str:
        """Build intent-focused context for Intent Recognition evaluation."""
        budget = budget or self.max_context_chars
        sections: List[str] = []

        intent_lines = ["INTENT REGISTER:"]
        for intent in self.intents:
            if intent.source == "agent_plan":
                continue
            line = (
                f"  [{intent.status.upper()}] {intent.name}: {intent.description} "
                f"(type={intent.requirement_type}, source={intent.source}, "
                f"first=step {intent.first_seen + 1}, "
                f"last=step {intent.last_seen + 1})"
            )
            intent_lines.append(line)
        if len(intent_lines) > 1:
            sections.append("\n".join(intent_lines))

        recency = self._get_recent_evidence(self._current_span_index())
        if recency:
            lines = ["RECENT CONTEXT:"]
            for fact in recency:
                line = (
                    f"  [Step {fact.span_index + 1}, {fact.fact_type}] {fact.content}"
                )
                lines.append(line)
            sections.append("\n".join(lines))

        user_facts = [f for f in self.evidence if f.fact_type == "user_statement"]
        if user_facts:
            lines = ["USER STATEMENTS:"]
            for fact in user_facts[-6:]:
                lines.append(f"  [Step {fact.span_index + 1}] {fact.content}")
            sections.append("\n".join(lines))

        result = "\n\n".join(sections)
        return result[:budget]

    def retrieve_for_relevancy(
        self, current_span: Dict[str, Any], *, budget: Optional[int] = None
    ) -> str:
        """Build reasoning-history context for Relevancy evaluation."""
        budget = budget or self.max_context_chars
        sections: List[str] = []

        recent_claims = self.claims[-12:]
        if recent_claims:
            lines = ["REASONING HISTORY (recent claims and decisions):"]
            for claim in recent_claims:
                line = (
                    f"  [Step {claim.span_index + 1}, {claim.claim_type}] "
                    f"({claim.entity_name}) {claim.content}"
                )
                lines.append(line)
            sections.append("\n".join(lines))

        recency = self._get_recent_evidence(self._current_span_index())
        if recency:
            lines = ["RECENT EVIDENCE:"]
            for fact in recency:
                line = (
                    f"  [Step {fact.span_index + 1}, {fact.fact_type}] {fact.content}"
                )
                lines.append(line)
            sections.append("\n".join(lines))

        result = "\n\n".join(sections)
        return result[:budget]

    def get_full_summary(self) -> str:
        """Complete trajectory summary for inter-step review."""
        sections: List[str] = []

        if self.coordination_context.inferred_topology != "unknown":
            sections.append(
                "COORDINATION:\n"
                f"  declared={self.coordination_context.declared_topology}\n"
                f"  inferred={self.coordination_context.inferred_topology}\n"
                f"  verification="
                f"{self.coordination_context.topology_verification}"
            )

        if self.policy_text:
            sections.append(f"POLICY:\n{self.policy_text[:2000]}")

        intent_lines = ["INTENT REGISTER:"]
        for intent in self.intents:
            event_summary = ", ".join(
                f"step {e['span_index'] + 1}:{e['type']}" for e in intent.events[-5:]
            )
            intent_lines.append(
                f"  [{intent.status.upper()}] {intent.name}: {intent.description} "
                f"(source={intent.source}, owners={intent.owner_agent_ids}, "
                f"assignment={intent.assignment_mode or 'unobserved'}, "
                f"events=[{event_summary}])"
            )
        sections.append("\n".join(intent_lines))

        if self.coordination_events:
            coordination_lines = ["COORDINATION HISTORY:"]
            for event in self.coordination_events[-20:]:
                coordination_lines.append(
                    f"  [Step {event.span_index + 1}, {event.event_type}] "
                    f"actor={event.actor_agent_id or 'unknown'} "
                    f"senders={event.sender_agent_ids} "
                    f"recipients={event.recipient_agent_ids} "
                    f"intents={event.related_intent_ids}"
                )
            sections.append("\n".join(coordination_lines))

        claim_lines = ["CLAIM HISTORY:"]
        for claim in self.claims[-20:]:
            claim_lines.append(
                f"  [Step {claim.span_index + 1}, {claim.claim_type}] "
                f"({claim.entity_name}) {claim.content[:200]}"
            )
        sections.append("\n".join(claim_lines))

        tool_facts = [f for f in self.evidence if f.fact_type == "tool_output"]
        if tool_facts:
            lines = ["KEY TOOL OUTPUTS:"]
            for fact in tool_facts[-10:]:
                lines.append(f"  [Step {fact.span_index + 1}] {fact.content[:300]}")
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    _INTERNAL_PREFIXES = ("REASONING:", "THOUGHT:", "PLAN:")
    _SYSTEM_PROMPT_MARKERS = (
        "you are a moderator",
        "you are an agent",
        "you are a coordinator",
        "available agents:",
    )

    def get_final_answer_context(self) -> Dict[str, Any]:
        """Return user-facing agent claims and all tool-output evidence for cross-validation."""
        user_facing: list[ClaimEntry] = []
        for claim in self.claims:
            if claim.claim_type not in ("assertion", "completion_claim"):
                continue
            text = claim.content.strip()
            if not text:
                continue
            if any(text.upper().startswith(p) for p in self._INTERNAL_PREFIXES):
                continue
            user_facing.append(claim)

        if self.latest_root_answer:
            final_answer = self.latest_root_answer
            final_answer_span_index = self.latest_root_answer_span_index
        elif self.coordination_context.final_response:
            final_answer = self.coordination_context.final_response
            final_answer_span_index = (
                self.coordination_context.final_response_event_index
            )
        elif user_facing:
            latest = user_facing[-1]
            final_answer = latest.content
            final_answer_span_index = latest.span_index
        else:
            final_answer = ""
            final_answer_span_index = -1

        user_facts: list[EvidenceFact] = []
        for fact in self.evidence:
            if fact.fact_type != "user_statement":
                continue
            text = fact.content.strip()
            lower = text.lower()
            if any(marker in lower for marker in self._SYSTEM_PROMPT_MARKERS):
                continue
            user_facts.append(fact)

        if not user_facts:
            user_question = ""
        elif len(user_facts) == 1:
            user_question = user_facts[0].content
        else:
            recent = user_facts[-8:]
            lines = [
                "Conversation user requests, most recent first; earlier context follows:"
            ]
            for fact in reversed(recent):
                lines.append(f"[User turn, step {fact.span_index + 1}] {fact.content}")
            user_question = "\n".join(lines)

        all_tool_outputs = [f for f in self.evidence if f.fact_type == "tool_output"]

        return {
            "final_answer": final_answer,
            "final_answer_span_index": final_answer_span_index,
            "user_question": user_question,
            "all_tool_outputs": all_tool_outputs,
            "coordination_context": self.coordination_context.compact_payload(),
        }

    def get_intent_events(self) -> List[Dict[str, Any]]:
        """Return intent tracking data for result building."""
        events: List[Dict[str, Any]] = []
        for intent_index, intent in enumerate(self.intents):
            for event in intent.events:
                events.append(
                    {
                        "intent_artifact_id": f"intent:{intent_index}",
                        "intent_name": intent.name,
                        "intent_description": intent.description,
                        "requirement_type": intent.requirement_type,
                        "intent_status": intent.status,
                        "owner_agent_ids": intent.owner_agent_ids,
                        "assigned_by_agent_id": intent.assigned_by_agent_id,
                        "assignment_mode": intent.assignment_mode,
                        "parent_intent_ids": intent.parent_intent_ids,
                        "dependency_intent_ids": intent.dependency_intent_ids,
                        "expected_output": intent.expected_output,
                        **event,
                    }
                )
        return events

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_span_index(self) -> int:
        non_policy = [f for f in self.evidence if f.fact_type != "policy_rule"]
        if non_policy:
            return max(f.span_index for f in non_policy) + 1
        return 0

    def _get_recent_evidence(self, current_idx: int) -> List[EvidenceFact]:
        non_policy = [f for f in self.evidence if f.fact_type != "policy_rule"]
        cutoff = current_idx - self.recency_window
        return [f for f in non_policy if f.span_index >= cutoff]


# ======================================================================
# Module-level helpers
# ======================================================================


def _safe_json(obj: Any, max_len: int | None = 1500) -> str:
    try:
        s = json.dumps(obj, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        s = str(obj)
    if max_len is None or len(s) <= max_len:
        return s
    return s[:max_len] + "..."


def _ordered_union(existing: List[str], additions: List[str]) -> List[str]:
    result = list(existing)
    for item in additions:
        normalized = str(item or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _safe_json(value, max_len=None)
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item.strip())
            elif isinstance(item, dict):
                candidate = item.get("text", item.get("content", item.get("value")))
                if candidate is not None:
                    text = _message_content(candidate)
                    if text:
                        parts.append(text)
        return "\n".join(part for part in parts if part)
    if value is None:
        return ""
    return str(value).strip()


def _normalise_message(message: Any) -> Optional[Dict[str, str]]:
    if isinstance(message, str):
        text = message.strip()
        return {"role": "user", "content": text} if text else None
    if not isinstance(message, dict):
        return None

    kwargs = message.get("kwargs") if isinstance(message.get("kwargs"), dict) else {}
    attributes = (
        message.get("attributes") if isinstance(message.get("attributes"), dict) else {}
    )
    role = (
        str(
            message.get("role")
            or message.get("type")
            or kwargs.get("role")
            or kwargs.get("type")
            or attributes.get("role")
            or attributes.get("type")
            or "user"
        )
        .strip()
        .lower()
    )
    role = {
        "human": "user",
        "ai": "assistant",
    }.get(role, role)
    content = _message_content(
        message.get("content")
        if message.get("content") is not None
        else kwargs.get("content", attributes.get("content"))
    )
    parts = message.get("parts")
    if not content and isinstance(parts, list):
        # OTel GenAI semconv: text lives in typed parts.
        content = _message_content(
            [
                part
                for part in parts
                if isinstance(part, dict)
                and part.get("type") not in {"tool_call", "function_call"}
            ]
        )
    has_tool_calls = bool(
        message.get("tool_calls")
        or kwargs.get("tool_calls")
        or _semconv_tool_call_parts(parts)
    )
    if not content and not has_tool_calls:
        return None
    return {"role": role, "content": content}


def _semconv_tool_call_parts(parts: Any) -> List[Dict[str, Any]]:
    return [
        part
        for part in (parts if isinstance(parts, list) else [])
        if isinstance(part, dict) and part.get("type") in {"tool_call", "function_call"}
    ]


def _extract_structured_messages(payload: Any) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    stack: List[Any] = [payload]
    visited: set[int] = set()
    while stack:
        current = stack.pop()
        if isinstance(current, (dict, list)):
            identity = id(current)
            if identity in visited:
                continue
            visited.add(identity)
        if isinstance(current, dict):
            raw_messages = current.get("messages")
            if isinstance(raw_messages, list):
                for message in raw_messages:
                    normalized = _normalise_message(message)
                    if normalized:
                        messages.append(normalized)
            for key, value in current.items():
                if key == "messages":
                    continue
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            for value in reversed(current):
                if isinstance(value, (dict, list)):
                    stack.append(value)
    return messages


def _extract_flattened_messages(
    payload: Dict[str, Any],
    prefix: str,
) -> List[Dict[str, str]]:
    indexed: Dict[int, Dict[str, str]] = {}
    role_re = re.compile(rf"^{re.escape(prefix)}\.(\d+)\.role$")
    content_re = re.compile(rf"^{re.escape(prefix)}\.(\d+)\.content$")
    for key, value in payload.items():
        role_match = role_re.match(key)
        content_match = content_re.match(key)
        if role_match:
            indexed.setdefault(int(role_match.group(1)), {})["role"] = (
                str(value).strip().lower()
            )
        elif content_match:
            indexed.setdefault(int(content_match.group(1)), {})["content"] = (
                _message_content(value)
            )
    return [
        {
            "role": entry.get(
                "role", "assistant" if "completion" in prefix else "user"
            ),
            "content": entry.get("content", ""),
        }
        for _, entry in sorted(indexed.items())
        if entry.get("content")
    ]


def _extract_prompt_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    messages = _extract_flattened_messages(payload, "gen_ai.prompt")
    messages.extend(_extract_structured_messages(payload))
    unique: List[Dict[str, str]] = []
    identities: set[tuple[str, str]] = set()
    for message in messages:
        identity = (message["role"], message["content"])
        if identity in identities:
            continue
        identities.add(identity)
        unique.append(message)
    return unique


def _exact_text_key(value: Any) -> str:
    """Identity key of a message or recorded payload; equal keys mean equal text.

    JSON text compares as its decoded value, without a ``{"value": ...}``
    wrapper; other text compares whole after ``_normalise_semantic_text``.
    """
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return _normalise_semantic_text(value)
    if isinstance(value, dict) and set(value) == {"value"}:
        return _exact_text_key(value["value"])
    if isinstance(value, str):
        return _normalise_semantic_text(value)
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _first_text_value(payload: Any, keys: tuple[str, ...]) -> str:
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key in keys:
                if key in current:
                    text = _message_content(current[key])
                    if text:
                        return text
            for value in current.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(
                value for value in reversed(current) if isinstance(value, (dict, list))
            )
    return ""


def _collect_tool_calls(payload: Any) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            raw_calls = current.get("tool_calls")
            if isinstance(raw_calls, dict):
                raw_calls = [raw_calls]
            if isinstance(raw_calls, list):
                calls.extend(item for item in raw_calls if isinstance(item, dict))
            calls.extend(_semconv_tool_call_parts(current.get("parts")))
            for key, value in current.items():
                if key != "tool_calls" and isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return calls


def _span_attributes(span_dict: Dict[str, Any]) -> Dict[str, Any]:
    attrs: Dict[str, Any] = {}
    raw_span = span_dict.get("raw_span_data")
    if isinstance(raw_span, dict):
        raw_attrs = raw_span.get("SpanAttributes") or raw_span.get("attributes")
        if isinstance(raw_attrs, dict):
            attrs.update(raw_attrs)
    explicit = span_dict.get("attributes")
    if isinstance(explicit, dict):
        attrs.update(explicit)
    return attrs


def _first_populated(attrs: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = attrs.get(key)
        if value not in (None, ""):
            return value
    return None


def _json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _coerce_optional_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _span_round_index(span_dict: Dict[str, Any]) -> Optional[int]:
    attrs = _span_attributes(span_dict)
    return _coerce_optional_int(
        _first_populated(
            attrs,
            "mas.round",
            "coordination.round",
            "agent.round",
            "round",
        )
    )


def _span_phase(span_dict: Dict[str, Any]) -> str:
    attrs = _span_attributes(span_dict)
    value = _first_populated(
        attrs,
        "mas.phase",
        "coordination.phase",
        "agent.phase",
        "phase",
    )
    return str(value or "").strip()


def _span_actor_scope(span_dict: Dict[str, Any]) -> str:
    attrs = _span_attributes(span_dict)
    role = (
        str(
            span_dict.get("agent_role")
            or _first_populated(attrs, "mas.agent.role", "agent.role")
            or ""
        )
        .strip()
        .lower()
    )
    if role in {"lead", "leader", "moderator", "orchestrator", "coordinator"}:
        return "root"
    if role in {
        "peer",
        "worker",
        "specialist",
        "reviewer",
        "verifier",
        "executor",
    }:
        return "peer"
    if _span_round_index(span_dict) is not None and role not in {
        "lead",
        "leader",
        "moderator",
        "orchestrator",
        "coordinator",
    }:
        return "peer"
    return ""


def _span_links(span_dict: Dict[str, Any]) -> List[Dict[str, str]]:
    raw_links = span_dict.get("links")
    if not isinstance(raw_links, list):
        raw_span = span_dict.get("raw_span_data")
        raw_span = raw_span if isinstance(raw_span, dict) else {}
        raw_links = raw_span.get("links")

    normalized: List[Dict[str, str]] = []
    if isinstance(raw_links, list):
        for link in raw_links:
            if not isinstance(link, dict):
                continue
            context = (
                link.get("context") if isinstance(link.get("context"), dict) else {}
            )
            attributes = (
                link.get("attributes")
                if isinstance(link.get("attributes"), dict)
                else {}
            )
            span_id = str(link.get("span_id") or context.get("span_id") or "")
            trace_id = str(link.get("trace_id") or context.get("trace_id") or "")
            link_type = str(
                _first_populated(
                    attributes,
                    "link.type",
                    "mas.link.type",
                    "ioa_observe.link.type",
                )
                or "untyped"
            )
            if span_id:
                normalized.append(
                    {
                        "span_id": span_id,
                        "trace_id": trace_id,
                        "link_type": link_type,
                        "from_agent": _link_from_agent(attributes),
                    }
                )
        return normalized

    raw_span = span_dict.get("raw_span_data")
    raw_span = raw_span if isinstance(raw_span, dict) else {}
    span_ids = raw_span.get("Links.SpanId") or raw_span.get("LinksSpanId") or []
    trace_ids = raw_span.get("Links.TraceId") or raw_span.get("LinksTraceId") or []
    attributes_list = (
        raw_span.get("Links.Attributes") or raw_span.get("LinksAttributes") or []
    )
    if not isinstance(span_ids, list):
        span_ids = _json_value(span_ids)
    if not isinstance(trace_ids, list):
        trace_ids = _json_value(trace_ids)
    if not isinstance(attributes_list, list):
        attributes_list = _json_value(attributes_list)
    for index, span_id in enumerate(span_ids if isinstance(span_ids, list) else []):
        attributes = (
            attributes_list[index]
            if isinstance(attributes_list, list)
            and index < len(attributes_list)
            and isinstance(attributes_list[index], dict)
            else {}
        )
        normalized.append(
            {
                "span_id": str(span_id),
                "trace_id": str(
                    trace_ids[index]
                    if isinstance(trace_ids, list) and index < len(trace_ids)
                    else ""
                ),
                "link_type": str(
                    _first_populated(
                        attributes,
                        "link.type",
                        "mas.link.type",
                        "ioa_observe.link.type",
                    )
                    or "untyped"
                ),
                "from_agent": _link_from_agent(attributes),
            }
        )
    return normalized


def _link_from_agent(attributes: Dict[str, Any]) -> str:
    return str(
        _first_populated(
            attributes,
            "link.from_agent",
            "mas.link.from_agent",
            "ioa_observe.link.from_agent",
        )
        or ""
    )


def _find_payload_values(payload: Any, keys: set[str]) -> List[str]:
    values: List[str] = []
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key.casefold() in keys and not isinstance(value, (dict, list)):
                    text = str(value or "").strip()
                    if text:
                        values.append(text)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return _ordered_union([], values)


def _span_recipient_agent_ids(span_dict: Dict[str, Any]) -> List[str]:
    attrs = _span_attributes(span_dict)
    recipients = [
        str(value)
        for value in (
            _first_populated(
                attrs,
                "mas.message.recipient",
                "mas.delegation.target",
                "messaging.destination.name",
                "coordination.recipient",
            ),
        )
        if value not in (None, "")
    ]
    recipients.extend(
        _find_payload_values(
            span_dict.get("input_payload"),
            {
                "recipient",
                "recipient_id",
                "recipient_agent_id",
                "target_agent",
                "target_agent_id",
                "assignee",
                "delegate_to",
            },
        )
    )
    return _ordered_union([], recipients)


def _infer_operation_recipient_agent_ids(
    span_dict: Dict[str, Any],
) -> List[str]:
    """Recover a handoff recipient when only the operation/result names it."""
    operation_name = str(span_dict.get("entity_name") or "")
    match = re.search(
        r"(?:delegate|assign|route|handoff|return|transfer)_to_(.+?)(?:\.tool)?$",
        operation_name,
        re.IGNORECASE,
    )
    recipients = [match.group(1)] if match else []
    recipients.extend(
        _find_payload_values(
            span_dict.get("output_payload"),
            {
                "agent_id",
                "recipient",
                "recipient_id",
                "recipient_agent_id",
                "target_agent",
                "target_agent_id",
            },
        )
    )
    actor_id = _normalise_actor_id(_span_agent_id(span_dict))
    return [
        recipient
        for recipient in _ordered_union([], recipients)
        if _normalise_actor_id(recipient) != actor_id
    ]


def _truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _normalise_operation_text(span_dict: Dict[str, Any]) -> str:
    attrs = _span_attributes(span_dict)
    return " ".join(
        str(value or "")
        for value in (
            _first_populated(
                attrs,
                "mas.operation.kind",
                "coordination.operation.kind",
                "operation.kind",
            ),
            span_dict.get("entity_name"),
        )
    ).casefold()


def _coordination_event_types(
    span_dict: Dict[str, Any],
    links: List[Dict[str, str]],
) -> List[str]:
    operation = _normalise_operation_text(span_dict)
    attrs = _span_attributes(span_dict)
    event_types: List[str] = []

    is_delegation = bool(re.search(r"\bdelegat\w*\b", operation))
    if re.search(r"\b(?:delegat|assign|route_to|routing)\w*\b", operation):
        event_types.append("assignment")
    if is_delegation or re.search(
        r"\b(?:handoff|hand_off|return_to|transfer)\w*\b",
        operation,
    ):
        event_types.append("handoff")
    role = str(
        span_dict.get("agent_role")
        or _first_populated(attrs, "mas.agent.role", "agent.role")
        or ""
    ).casefold()
    operation_kind = str(
        _first_populated(
            attrs,
            "mas.operation.kind",
            "coordination.operation.kind",
            "operation.kind",
        )
        or ""
    ).casefold()
    entity_name = str(span_dict.get("entity_name") or "").casefold()
    actor_agent_id = _normalise_actor_id(_span_agent_id(span_dict))
    is_assignment_or_handoff = any(
        event_type in {"assignment", "handoff"} for event_type in event_types
    )
    explicit_verification = bool(
        re.search(r"\b(?:verif|validat|review|critic|check)\w*\b", operation_kind)
        or re.match(r"(?:verif|validat|review|critic|check)\w*", entity_name)
        or role in {"critic", "reviewer", "verifier", "validator"}
        or re.match(
            r"(?:critic|reviewer|verifier|validator)(?:[_\-.].*)?$",
            actor_agent_id,
        )
    )
    if explicit_verification and not (
        is_assignment_or_handoff
        and role not in {"critic", "reviewer", "verifier", "validator"}
    ):
        event_types.append("verification")
    if re.search(r"\b(?:select|vote|consensus|winner)\w*\b", operation):
        event_types.append("selection")
    if re.search(
        r"\b(?:synthesi|aggregate|final_response|materiali)\w*\b", operation
    ) or _truthy(_first_populated(attrs, "mas.response.final", "response.final")):
        event_types.append("synthesis")
    if re.search(
        r"\b(?:commit|state_write|apply_action|run_action|execute_action)\w*\b",
        operation,
    ):
        event_types.append("commit")

    if links:
        typed_links = " ".join(link["link_type"].casefold() for link in links)
        if re.search(r"handoff|delegat|transfer", typed_links):
            event_types.append("handoff")
        elif re.search(
            r"peer|message|context|influence|blackboard|pipeline|coordination",
            typed_links,
        ):
            event_types.append("peer_message")
    if _payload_contains_coordination_context(span_dict.get("input_payload")):
        event_types.append("peer_message")
    if _is_revision_span(span_dict):
        event_types.append("revision")
    return _ordered_union([], event_types)


def _is_revision_span(span_dict: Dict[str, Any]) -> bool:
    operation = _normalise_operation_text(span_dict)
    if re.search(r"\b(?:revis|refin|critique|reconsider)\w*\b", operation):
        return True
    return (
        span_dict.get("entity_type") == "llm"
        and (_span_round_index(span_dict) or 0) > 1
        and (
            bool(_span_links(span_dict))
            or _payload_contains_coordination_context(span_dict.get("input_payload"))
        )
    )


def _span_operation_status(span_dict: Dict[str, Any]) -> str:
    if span_dict.get("contains_error"):
        return "error"
    values = _find_payload_values(
        span_dict.get("output_payload"),
        {"status", "outcome", "result_status"},
    )
    return values[0] if values else "observed"


def _coordination_event_status(span_dict: Dict[str, Any], event_type: str) -> str:
    """Return an event-level outcome while preserving generic span status."""
    if event_type == "verification":
        output_text = _extract_agent_output(span_dict.get("output_payload") or {})
        match = re.search(
            r"\bverification\s*:\s*(approved|flagged|rejected)\b",
            output_text,
            flags=re.IGNORECASE,
        )
        if match:
            return match.group(1).casefold()
    return _span_operation_status(span_dict)


def _coordination_content(span_dict: Dict[str, Any]) -> str:
    input_payload = span_dict.get("input_payload")
    output_payload = span_dict.get("output_payload")
    summary: Dict[str, Any] = {}
    for label, payload in (("input", input_payload), ("output", output_payload)):
        if not isinstance(payload, dict):
            continue
        summary[f"{label}_fields"] = sorted(str(key) for key in payload)
        selected: Dict[str, Any] = {}
        for key in (
            "task",
            "objective",
            "instruction",
            "message",
            "expected_output",
            "deliverable",
            "recipient",
            "from",
            "winning_agent",
            "selection_method",
            "decision",
            "status",
            "outcome",
        ):
            value = payload.get(key)
            if value not in (None, "") and not isinstance(value, (dict, list)):
                selected[key] = value
        if selected:
            summary[label] = selected
    return _safe_json(summary, max_len=None)


def _span_expected_output(content: str) -> str:
    try:
        payload = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return ""
    return _first_text_value(
        payload,
        ("expected_output", "deliverable", "success_criteria", "response_format"),
    )


def _span_work_description(span_dict: Dict[str, Any]) -> str:
    return _first_text_value(
        span_dict.get("input_payload"),
        (
            "task",
            "objective",
            "instruction",
            "request",
            "query",
            "message",
            "description",
            "content",
        ),
    )


def _span_expected_output_from_payload(span_dict: Dict[str, Any]) -> str:
    return _first_text_value(
        span_dict.get("input_payload"),
        ("expected_output", "deliverable", "success_criteria", "response_format"),
    )


def _span_intent_references(
    span_dict: Dict[str, Any],
    *,
    dependency: bool,
) -> List[str]:
    keys = (
        {
            "dependencies",
            "dependency",
            "dependency_ids",
            "dependency_intent_ids",
            "depends_on",
            "prerequisites",
        }
        if dependency
        else {
            "parent",
            "parent_id",
            "parent_intent_id",
            "parent_intent_ids",
            "parent_task_id",
            "parent_work_item_id",
        }
    )
    values: List[str] = []
    stack: List[Any] = [span_dict.get("input_payload")]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if key.casefold() in keys:
                    values.extend(_reference_strings(value))
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return _ordered_union([], values)


def _reference_strings(value: Any) -> List[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        return [item for nested in value for item in _reference_strings(nested)]
    if isinstance(value, dict):
        for key in (
            "intent_id",
            "task_id",
            "work_item_id",
            "id",
            "name",
            "description",
        ):
            if key in value:
                references = _reference_strings(value[key])
                if references:
                    return references
    return []


def _normalise_semantic_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value or "").casefold()))


def _extract_user_messages(input_payload: Dict[str, Any]) -> List[str]:
    """Pull user messages from flattened or native structured payloads."""
    messages = _extract_prompt_messages(input_payload)
    user_messages = [
        message["content"]
        for message in messages
        if message["role"] in {"user", "human"} and message["content"]
    ]
    if not user_messages:
        fallback = _first_text_value(
            input_payload,
            ("user_message", "question", "query", "task", "instruction"),
        )
        if fallback:
            user_messages.append(fallback)
    return _ordered_union([], user_messages)


_COORDINATION_CONTEXT_KEYS = {
    "blackboard_entries",
    "candidate_answers",
    "consensus_record",
    "handoff",
    "handoff_context",
    "messages_by_agent",
    "peer_answers",
    "peer_messages",
    "pipeline_handoff",
    "prior_agent_outputs",
    "review_feedback",
    "shared_context",
}

_AGENT_OUTPUT_MAP_KEYS = {
    "blackboard_entries",
    "candidate_answers",
    "final_round_answers",
    "messages_by_agent",
    "peer_answers",
    "peer_messages",
    "prior_agent_outputs",
}

_EMBEDDED_USER_REQUEST_RE = re.compile(
    r"(?:original\s+)?user\s+request\s*:\s*(.+?)(?:\n\s*begin!?\s*$|$)",
    re.IGNORECASE | re.DOTALL,
)


def _payload_contains_coordination_context(payload: Any) -> bool:
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if _COORDINATION_CONTEXT_KEYS.intersection(
                str(key).casefold() for key in current
            ):
                return True
            stack.extend(
                value for value in current.values() if isinstance(value, (dict, list))
            )
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return False


def _payload_agent_references(payload: Any) -> List[str]:
    """Collect agent IDs named as sources in structured coordination input."""
    agent_ids: List[str] = []
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                normalized_key = str(key).casefold()
                if normalized_key in _AGENT_OUTPUT_MAP_KEYS and isinstance(value, dict):
                    agent_ids.extend(str(agent_id) for agent_id in value)
                elif normalized_key in {
                    "from",
                    "sender",
                    "sender_agent_id",
                    "source_agent",
                    "source_agent_id",
                    "winning_agent",
                } and not isinstance(value, (dict, list)):
                    agent_ids.append(str(value))
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return _ordered_union([], agent_ids)


def _extract_embedded_user_request(text: str) -> str:
    """Extract an external request carried inside an agent task envelope."""
    match = _EMBEDDED_USER_REQUEST_RE.search(str(text or "").strip())
    return match.group(1).strip() if match else ""


def _is_coordination_context_message(text: str) -> bool:
    """Identify machine-injected peer, handoff, review, or shared context."""
    normalized = " ".join(str(text or "").casefold().split())
    if _extract_embedded_user_request(text) and any(
        marker in normalized
        for marker in (
            "objective and guidance",
            "coordination round",
            "guidance from the lead",
        )
    ):
        return True
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return False
    return _payload_contains_coordination_context(payload)


def _is_runtime_feedback_message(text: str) -> bool:
    """Identify tool/runtime feedback represented as a user-role message."""
    normalized = " ".join(str(text or "").casefold().split())
    if not re.match(
        r"^(?:error|warning|budget warning|step warning|system notice):",
        normalized,
    ):
        return False
    return any(
        marker in normalized
        for marker in (
            "available tools",
            "completion tool",
            "continue or submit",
            "steps remain",
            "tool call",
            "use one of the",
        )
    )


def _extract_system_messages(input_payload: Dict[str, Any]) -> List[str]:
    """Pull system messages from flattened or native structured payloads."""
    messages = _extract_prompt_messages(input_payload)
    system_messages = [
        message["content"]
        for message in messages
        if message["role"] == "system" and message["content"]
    ]
    explicit = _first_text_value(input_payload, ("system_prompt", "system_message"))
    if explicit:
        system_messages.append(explicit)
    return _ordered_union([], system_messages)


def _normalized_contract_text(text: str) -> str:
    """Normalize a system contract for stable root-agent identity checks."""
    return " ".join(text.split()).casefold()


def _is_delegated_agent_input(
    input_payload: Dict[str, Any],
    *,
    root_policy_text: str = "",
) -> bool:
    """Distinguish a peer-agent task from an external user turn.

    The root policy is extracted once from the trajectory and is a more stable
    identity signal than role-specific words such as ``moderator``.  Keep the
    marker fallback for callers that construct a context without policy text.
    """
    system_messages = _extract_system_messages(input_payload)
    system_text = " ".join(system_messages)
    if not system_text:
        return False

    normalized_root = _normalized_contract_text(root_policy_text)
    if normalized_root and any(
        _normalized_contract_text(message) == normalized_root
        for message in system_messages
    ):
        return False

    normalized_system = _normalized_contract_text(system_text)
    moderator_markers = (
        "you are a moderator",
        "you are a coordinator",
        "coordinating a team",
        "available agents",
        "delegate sub-tasks",
    )
    return not any(marker in normalized_system for marker in moderator_markers)


def _unique_intent_name(name: str, existing_names: set[str]) -> str:
    if name not in existing_names:
        return name
    suffix = 2
    while f"{name} {suffix}" in existing_names:
        suffix += 1
    return f"{name} {suffix}"


def _extract_agent_output(output_payload: Dict[str, Any]) -> str:
    """Pull assistant content and tool decisions from supported payload shapes."""
    messages = _extract_flattened_messages(output_payload, "gen_ai.completion")
    messages.extend(_extract_structured_messages(output_payload))
    parts = [
        message["content"]
        for message in messages
        if message["role"] in {"assistant", "ai"} and message["content"]
    ]
    if not parts:
        fallback = _first_text_value(
            output_payload,
            ("final_answer", "answer", "response", "content", "output"),
        )
        if fallback:
            parts.append(fallback)

    tool_calls = _collect_tool_calls(output_payload)
    if tool_calls:
        parts.append(f"Tool calls: {_safe_json(tool_calls, max_len=None)}")
    return "\n".join(_ordered_union([], parts))


def _has_visible_content(text: str) -> bool:
    visible = re.sub(
        r"<\|?channel\|?>\s*(?:thought|analysis)?",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()
    return bool(visible)


def _span_agent_id(span_dict: Dict[str, Any]) -> str:
    raw_span = span_dict.get("raw_span_data")
    raw_span = raw_span if isinstance(raw_span, dict) else {}
    attrs = raw_span.get("SpanAttributes")
    attrs = attrs if isinstance(attrs, dict) else {}
    generic_agent = str(attrs.get("agent_id") or raw_span.get("agent_id") or "")
    if re.search(r"[.()/\s]", generic_agent):
        # A method path such as ``moderator.invoke`` is not an agent name.
        generic_agent = ""
    for value in (
        span_dict.get("agent_id"),
        attrs.get("mas.agent.id"),
        attrs.get("agent.id"),
        generic_agent,
        attrs.get("application_id"),
        span_dict.get("app_name"),
        raw_span.get("ServiceName"),
    ):
        normalized = str(value or "").strip()
        if normalized and normalized.casefold() != "unknown":
            return normalized
    return ""


def _normalise_actor_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


# ----------------------------------------------------------------------
# Work, flag and outcome helpers (deterministic, framework-neutral)
# ----------------------------------------------------------------------

_RETRYABLE_OUTCOMES = {
    "failed",
    "needs_input",
    "no_response",
    "declined",
    "waiting",
    "unfinished",
}
# Router outputs that end the run rather than assign work.
_TERMINAL_ROUTES = {
    "end",
    "__end__",
    "finish",
    "finished",
    "final",
    "final_answer",
    "done",
    "stop",
    "terminate",
}
# One line of an allocator roster table: ``- agent_id: capability``.
_CAPABILITY_LINE_RE = re.compile(
    r"^[ \t]*[-*•][ \t]*(?P<agent>[A-Za-z][\w.\-]{1,60})[ \t]*:[ \t]*"
    r"(?P<capability>[^\n]{8,})$",
    re.MULTILINE,
)
_DELEGATION_FAILED_RE = re.compile(
    r"^\s*\[delegation\][^\n]*\bfailed\b",
    re.IGNORECASE,
)
_FLAG_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    (
        # First person only: "threads hang while waiting for the gateway"
        # describes a system, not an agent that is blocked.
        "waiting",
        re.compile(
            r"\b(?:I|we)(?:'ll| will| shall| am going to| are going to) wait\b"
            r"|\b(?:I|we)(?:'m| am|'re| are) (?:still |currently )?waiting\b"
            r"|\b(?:I|we)(?:'ll| will| can)\b[^.\n]{0,80}?\bonce (?!you\b)(?:the |an? )?"
            r"[\w -]{0,40}?(?:provides?|responds?|returns?|replies|reply"
            r"|is available|has (?:provided|finished))\b"
            r"|\bonce (?!you\b)(?:the |an? )?[\w -]{0,40}?(?:provides?|responds?"
            r"|returns?|replies|reply|is available|has (?:provided|finished))\b"
            r"[^.\n]{0,80}?\b(?:I|we)(?:'ll| will| can)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "needs_input",
        re.compile(
            r"\b(?:please (?:provide|share|specify|clarify|send)"
            r"|(?:could|can) you (?:please )?(?:provide|share|specify|clarify|send)"
            r"|(?:I|we) (?:would )?(?:need|require) (?:some |more |additional "
            r"|further |the following )?(?:information|details|input|data|context)"
            r"|before (?:I|we) can (?:proceed|continue|complete|finish|start)"
            r"|if you (?:can )?provide)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cannot_do",
        re.compile(
            r"\b(?:I|we)(?: cannot| can't| can not| couldn't| could not"
            r"|(?:'m| am| was|'re| are| were) (?:unable|not able) to)"
            r" (?:complete|perform|do|carry out|access|retrieve|fetch|obtain|get"
            r"|provide|calculate|compute|determine|book|process|proceed|continue"
            r"|fulfil+|help|answer|verify|look up|query|execute|run|finish"
            r"|finalize|generate|produce|create|plan|check)\b"
            r"|\b(?:I|we) (?:do not|don't) have (?:access|the ability|the tools?"
            r"|permission)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "out_of_scope",
        re.compile(
            r"\b(?:(?:is |are )?not (?:my|within my|in my|part of my)"
            r" (?:responsibility|role|scope|job|remit)"
            r"|outside (?:of )?(?:my|the) (?:scope|role|responsibilit\w+|remit)"
            r"|not the one in charge"
            r"|(?:is|are) handled by (?:another|the other|a different) agent)\b",
            re.IGNORECASE,
        ),
    ),
)


def _flag_matches(text: str) -> List[tuple[str, str]]:
    """Return ``(kind, quote)`` for self-reported blocks in an agent's text."""
    body = str(text or "")
    if not body.strip():
        return []
    matches: List[tuple[str, str]] = []
    for kind, pattern in _FLAG_PATTERNS:
        match = pattern.search(body)
        if not match:
            continue
        start = max(0, body.rfind(".", 0, match.start()) + 1)
        end_candidates = [
            index
            for index in (body.find(".", match.end()), body.find("\n", match.end()))
            if index >= 0
        ]
        end = min(end_candidates) + 1 if end_candidates else len(body)
        matches.append((kind, body[start:end].strip()[:400]))
    return matches


def _classify_work_response(
    text: str, *, contains_error: bool = False
) -> tuple[str, str]:
    """Map a recipient's reply to a ``WorkUnit.outcome`` and the reason."""
    stripped = str(text or "").strip()
    if contains_error:
        return "failed", "error_status"
    if not stripped or stripped.casefold() in {"null", "none", "{}", "[]", '""'}:
        return "no_response", "empty_reply"
    if _DELEGATION_FAILED_RE.search(stripped):
        return "failed", "delegation_failed"
    try:
        parsed = json.loads(stripped)
    except (TypeError, json.JSONDecodeError):
        parsed = None
    if (
        isinstance(parsed, dict)
        and parsed.get("error")
        and not any(
            parsed.get(key) for key in ("content", "result", "answer", "response")
        )
    ):
        return "failed", "error_payload"
    kinds = [kind for kind, _ in _flag_matches(stripped)]
    if "waiting" in kinds:
        return "waiting", "waiting_reply"
    if "needs_input" in kinds:
        return "needs_input", "needs_input_reply"
    if kinds and set(kinds) <= {"cannot_do", "out_of_scope"}:
        return "declined", "declined_reply"
    return "completed", "reply"


def _is_tool_call_only(text: str) -> bool:
    """True when an output only requests tool calls and says nothing else."""
    visible = re.sub(
        r"<\|?channel\|?>\s*(?:thought|analysis)?",
        "",
        str(text or ""),
        flags=re.IGNORECASE,
    ).strip()
    if visible.startswith("Tool calls:"):
        return True
    if not visible.startswith("{"):
        return False
    try:
        parsed = json.loads(visible)
    except (TypeError, json.JSONDecodeError):
        return False
    return (
        isinstance(parsed, dict)
        and isinstance(parsed.get("tool_calls"), list)
        and bool(parsed["tool_calls"])
        and not any(
            isinstance(parsed.get(key), str) and parsed[key].strip()
            for key in ("content", "text", "message")
        )
    )


def _requested_tool_names(payload: Any) -> List[str]:
    """Return tool names an LLM output asked to call, across schemas."""
    names: List[str] = []
    if isinstance(payload, dict):
        flattened = re.compile(
            r"^gen_ai\.completion\.\d+\.tool_calls\.\d+\.(?:name|function\.name)$"
        )
        names.extend(
            str(value)
            for key, value in sorted(payload.items())
            if flattened.match(str(key)) and value
        )
    for call in _collect_tool_calls(payload):
        function = call.get("function")
        name = function.get("name") if isinstance(function, dict) else call.get("name")
        if name:
            names.append(str(name))
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if current.get("type") in {"tool_call", "function_call"} and current.get(
                "name"
            ):
                names.append(str(current["name"]))
            stack.extend(
                value for value in current.values() if isinstance(value, (dict, list))
            )
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return _ordered_union([], names)


def _requested_tool_call_ids(payload: Any) -> List[str]:
    """Return the ids of the tool calls an LLM output requested."""
    ids: List[str] = []
    if isinstance(payload, dict):
        flattened = re.compile(r"^gen_ai\.completion\.\d+\.tool_calls\.\d+\.id$")
        ids.extend(
            str(value)
            for key, value in sorted(payload.items())
            if flattened.match(str(key)) and value
        )
    ids.extend(
        str(call["id"]) for call in _collect_tool_calls(payload) if call.get("id")
    )
    stack: List[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            if current.get("type") in {"tool_call", "function_call"} and current.get(
                "id"
            ):
                ids.append(str(current["id"]))
            stack.extend(
                value for value in current.values() if isinstance(value, (dict, list))
            )
        elif isinstance(current, list):
            stack.extend(value for value in current if isinstance(value, (dict, list)))
    return _ordered_union([], ids)


def _reply_without_tool_calls(text: str) -> str:
    """The agent's own words, without the tool-call listing or envelope."""
    body = str(text or "")
    if _is_tool_call_only(body):
        return ""
    marker = body.find("Tool calls: ")
    if marker >= 0 and (marker == 0 or body[marker - 1] == "\n"):
        body = body[:marker]
    return body.strip()


# Operation names such as ``route_to_agent`` name a mechanism, not an agent.
_GENERIC_ROUTE_TARGETS = {
    "agent",
    "agents",
    "next",
    "next_agent",
    "node",
    "tool",
    "tools",
    "user",
    "human",
}


def _declared_recipient_ids(span_dict: Dict[str, Any]) -> set[str]:
    """Recipients a span names explicitly (attributes or operation name)."""
    attrs = _span_attributes(span_dict)
    declared = {
        str(value)
        for value in (
            _first_populated(
                attrs,
                "mas.message.recipient",
                "mas.delegation.target",
                "messaging.destination.name",
                "coordination.recipient",
            ),
        )
        if value not in (None, "")
    }
    match = re.search(
        r"(?:delegate|assign|route|handoff|return|transfer)_to_(.+?)(?:\.tool)?$",
        str(span_dict.get("entity_name") or ""),
        re.IGNORECASE,
    )
    if match and match.group(1).casefold() not in _GENERIC_ROUTE_TARGETS:
        declared.add(match.group(1))
    return declared


def _tool_reply_text(output_payload: Any) -> str:
    if output_payload is None:
        return ""
    if isinstance(output_payload, str):
        return output_payload.strip()
    if isinstance(output_payload, dict):
        text = _first_text_value(
            output_payload,
            ("value", "content", "result", "response", "output", "answer"),
        )
        if text:
            return text
    return _safe_json(output_payload, max_len=None)


def _tool_outcome(span_dict: Dict[str, Any], output_payload: Any) -> str:
    """Classify a tool execution as ``output``, ``error`` or ``no_output``."""
    if span_dict.get("contains_error"):
        return "error"
    if output_payload in (None, "", {}, []):
        return "no_output"
    if isinstance(output_payload, dict):
        status = str(output_payload.get("status", "")).casefold()
        if status in {"error", "failed", "failure"}:
            return "error"
        if output_payload.get("error") and not any(
            output_payload.get(key) for key in ("result", "content", "data")
        ):
            return "error"
        values = [value for value in output_payload.values() if value not in (None, "")]
        if not values:
            return "no_output"
    text = _tool_reply_text(output_payload)
    if _DELEGATION_FAILED_RE.search(text):
        return "error"
    if text.casefold() in {"null", "none"}:
        return "no_output"
    return "output"


def _span_call_id(span_dict: Dict[str, Any]) -> str:
    attrs = _span_attributes(span_dict)
    for key in ("mas.call.id", "gen_ai.tool.call.id", "tool_call_id", "tool.call.id"):
        value = attrs.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


_TIMESTAMP_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d+))?(?P<zone>Z|[+-]\d{2}:?\d{2})?$"
)


def _timestamp_ns(value: Any) -> Optional[int]:
    """Parse epoch numbers and ISO / ``YYYY-MM-DD HH:MM:SS.fffffffff`` strings."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _epoch_to_ns(value)
    if isinstance(value, float):
        return _epoch_to_ns(value) if math.isfinite(value) else None
    text = str(value).strip()
    if re.fullmatch(r"\d+", text):
        # Integers stay exact; float() would round nanoseconds.
        return _epoch_to_ns(int(text))
    try:
        number = float(text)
    except ValueError:
        number = None
    if number is not None:
        return _epoch_to_ns(number) if math.isfinite(number) else None
    match = _TIMESTAMP_RE.match(text)
    if not match:
        return None
    from datetime import datetime, timezone

    try:
        base = datetime.strptime(
            f"{match.group('date')} {match.group('time')}",
            "%Y-%m-%d %H:%M:%S",
        )
    except ValueError:
        return None
    zone = match.group("zone")
    offset_seconds = 0
    if zone and zone != "Z":
        sign = 1 if zone[0] == "+" else -1
        digits = zone[1:].replace(":", "")
        offset_seconds = sign * (int(digits[:2]) * 3600 + int(digits[2:4]) * 60)
    seconds = int(base.replace(tzinfo=timezone.utc).timestamp()) - offset_seconds
    fraction = (match.group("fraction") or "0")[:9].ljust(9, "0")
    return seconds * 1_000_000_000 + int(fraction)


def _span_duration_ns(span_dict: Dict[str, Any]) -> Optional[int]:
    """Read the OTel span ``Duration``, which is recorded in nanoseconds."""
    raw_span = span_dict.get("raw_span_data")
    value = raw_span.get("Duration") if isinstance(raw_span, dict) else None
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return int(duration) if math.isfinite(duration) and duration >= 0 else None


def _epoch_to_ns(number: int | float) -> int:
    """Scale an epoch in s, ms, us or ns to ns."""
    if number > 1e17:
        return int(number)
    if number > 1e14:
        return int(number * 1_000)
    if number > 1e11:
        return int(number * 1_000_000)
    return int(number * 1_000_000_000)
