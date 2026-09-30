#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Load a persisted trajectory-context artifact for metric-only evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from stateful_evals_be.evaluation.trajectory_context import (
    AgentProfile,
    ArtifactProvenanceLink,
    ClaimEntry,
    CoordinationEvent,
    EvidenceFact,
    FlagEntry,
    IntentEntry,
    TrajectoryContext,
    WorkUnit,
)
from stateful_evals_be.evaluation.coordination import CoordinationContext


def load_trajectory_context_artifact(
    path: str | Path,
) -> tuple[TrajectoryContext, dict[str, Any]]:
    """Restore ``TrajectoryContext`` from the evaluator's JSON artifact."""
    artifact_path = Path(path).expanduser()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Trajectory context artifact must contain a JSON object")

    evidence_payload = _items(payload.get("evidence"))
    policy_text = str(payload.get("policy_text") or "").strip()
    if not policy_text:
        policy_text = next(
            (
                str(item.get("content") or "")
                for item in evidence_payload
                if item.get("fact_type") == "policy_rule"
                and item.get("source_name") == "policy"
            ),
            "",
        )

    context = TrajectoryContext(
        policy_text="",
        coordination_context=CoordinationContext.from_payload(
            payload.get("coordination_context")
        ),
    )
    adapter_intents = list(context.intents)
    adapter_events = list(context.coordination_events)
    adapter_metadata = dict(context.coordination_metadata)
    context.policy_text = policy_text
    context.evidence = [
        EvidenceFact(
            span_index=_integer(item.get("span_index"), -1),
            fact_type=str(item.get("fact_type") or ""),
            content=str(item.get("content") or ""),
            source_name=str(item.get("source_name") or ""),
            agent_id=str(item.get("agent_id") or ""),
            actor_scope=str(item.get("actor_scope") or ""),
            span_id=str(item.get("span_id") or ""),
            parent_span_id=str(item.get("parent_span_id") or ""),
            trace_id=str(item.get("trace_id") or ""),
            related_intent_ids=_string_list(item.get("related_intent_ids")),
            work_id=str(item.get("work_id") or ""),
            outcome=str(item.get("outcome") or ""),
            relayed_from_agent_id=str(item.get("relayed_from_agent_id") or ""),
            started_at_ns=_optional_integer(item.get("started_at_ns")),
            duration_ns=_optional_integer(item.get("duration_ns")),
        )
        for item in evidence_payload
    ]
    loaded_intents = [
        IntentEntry(
            name=str(item.get("name") or ""),
            source=str(item.get("source") or ""),
            first_seen=_integer(item.get("first_seen"), -1),
            last_seen=_integer(item.get("last_seen"), -1),
            status=str(item.get("status") or ""),
            description=str(item.get("description") or ""),
            requirement_type=str(item.get("requirement_type") or "request"),
            events=[
                dict(event)
                for event in item.get("events") or []
                if isinstance(event, Mapping)
            ],
            owner_agent_ids=_string_list(item.get("owner_agent_ids")),
            assigned_by_agent_id=str(item.get("assigned_by_agent_id") or ""),
            assignment_mode=str(item.get("assignment_mode") or ""),
            parent_intent_ids=_string_list(item.get("parent_intent_ids")),
            dependency_intent_ids=_string_list(item.get("dependency_intent_ids")),
            expected_output=str(item.get("expected_output") or ""),
            phase=str(item.get("phase") or ""),
            round_index=_optional_integer(item.get("round_index")),
        )
        for item in _items(payload.get("intents"))
    ]
    context.intents = loaded_intents
    context.claims = [
        ClaimEntry(
            span_index=_integer(item.get("span_index"), -1),
            claim_type=str(item.get("claim_type") or ""),
            content=str(item.get("content") or ""),
            entity_name=str(item.get("entity_name") or ""),
            agent_id=str(item.get("agent_id") or ""),
            actor_scope=str(item.get("actor_scope") or ""),
            span_id=str(item.get("span_id") or ""),
            parent_span_id=str(item.get("parent_span_id") or ""),
            trace_id=str(item.get("trace_id") or ""),
            related_intent_ids=_string_list(item.get("related_intent_ids")),
            evidence_refs=_string_list(item.get("evidence_refs")),
            revision_of_claim_id=str(item.get("revision_of_claim_id") or ""),
            phase=str(item.get("phase") or ""),
            round_index=_optional_integer(item.get("round_index")),
            work_id=str(item.get("work_id") or ""),
            outcome=str(item.get("outcome") or ""),
            relayed_from_agent_id=str(item.get("relayed_from_agent_id") or ""),
        )
        for item in _items(payload.get("claims"))
    ]
    loaded_coordination_events = [
        CoordinationEvent(
            event_id=str(item.get("event_id") or f"coordination:{index}"),
            span_index=_integer(item.get("span_index"), -1),
            event_type=str(item.get("event_type") or ""),
            operation_name=str(item.get("operation_name") or ""),
            actor_agent_id=str(item.get("actor_agent_id") or ""),
            sender_agent_ids=_string_list(item.get("sender_agent_ids")),
            recipient_agent_ids=_string_list(item.get("recipient_agent_ids")),
            related_intent_ids=_string_list(item.get("related_intent_ids")),
            input_artifact_ids=_string_list(item.get("input_artifact_ids")),
            output_artifact_ids=_string_list(item.get("output_artifact_ids")),
            linked_span_ids=_string_list(item.get("linked_span_ids")),
            link_types=_string_list(item.get("link_types")),
            assignment_mode=str(item.get("assignment_mode") or ""),
            status=str(item.get("status") or ""),
            content=str(item.get("content") or ""),
            phase=str(item.get("phase") or ""),
            round_index=_optional_integer(item.get("round_index")),
            span_id=str(item.get("span_id") or ""),
            parent_span_id=str(item.get("parent_span_id") or ""),
            trace_id=str(item.get("trace_id") or ""),
            work_id=str(item.get("work_id") or ""),
            outcome=str(item.get("outcome") or ""),
            source_event_index=_optional_integer(item.get("source_event_index")),
        )
        for index, item in enumerate(_items(payload.get("coordination_events")))
    ]
    intent_id_map: dict[str, str] = {}
    if loaded_coordination_events:
        context.coordination_events = loaded_coordination_events
    else:
        existing_intents = {
            (
                intent.name,
                intent.description,
                tuple(intent.owner_agent_ids),
            ): index
            for index, intent in enumerate(context.intents)
        }
        for adapter_index, intent in enumerate(adapter_intents):
            identity = (
                intent.name,
                intent.description,
                tuple(intent.owner_agent_ids),
            )
            target_index = existing_intents.get(identity)
            if target_index is None:
                target_index = len(context.intents)
                context.intents.append(intent)
                existing_intents[identity] = target_index
            intent_id_map[f"intent:{adapter_index}"] = f"intent:{target_index}"
        for intent in adapter_intents:
            intent.parent_intent_ids = [
                intent_id_map.get(intent_id, intent_id)
                for intent_id in intent.parent_intent_ids
            ]
            intent.dependency_intent_ids = [
                intent_id_map.get(intent_id, intent_id)
                for intent_id in intent.dependency_intent_ids
            ]
        for event in adapter_events:
            event.related_intent_ids = [
                intent_id_map.get(intent_id, intent_id)
                for intent_id in event.related_intent_ids
            ]
        context.coordination_events = adapter_events
    context.provenance_links = [
        ArtifactProvenanceLink(
            source_artifact_id=str(item.get("source_artifact_id") or ""),
            target_artifact_id=str(item.get("target_artifact_id") or ""),
            relation_type=str(item.get("relation_type") or ""),
            span_index=_integer(item.get("span_index"), -1),
            span_id=str(item.get("span_id") or ""),
            trace_id=str(item.get("trace_id") or ""),
            metadata=(
                dict(item.get("metadata"))
                if isinstance(item.get("metadata"), Mapping)
                else {}
            ),
        )
        for item in _items(payload.get("provenance_links"))
    ]
    raw_coordination_metadata = payload.get("coordination_metadata")
    context.coordination_metadata = dict(adapter_metadata)
    if isinstance(raw_coordination_metadata, Mapping):
        context.coordination_metadata.update(dict(raw_coordination_metadata))

    final_context = payload.get("final_answer_context")
    if not isinstance(final_context, Mapping):
        final_context = {}
    loaded_final_answer = str(
        final_context.get("final_answer") or payload.get("latest_root_answer") or ""
    )
    if loaded_final_answer:
        context.latest_root_answer = loaded_final_answer
        context.latest_root_answer_span_index = _integer(
            final_context.get(
                "final_answer_span_index",
                payload.get("latest_root_answer_span_index"),
            ),
            -1,
        )
    loaded_agents = _load_records(payload.get("agents"), AgentProfile)
    if loaded_agents:
        context.agents = {profile.agent_id: profile for profile in loaded_agents}
    if "work_units" in payload:
        context.work_units = _load_records(payload.get("work_units"), WorkUnit)
    elif loaded_coordination_events:
        # An artifact saved before work state existed: units rebuilt from its
        # sidecar would cite adapter events the loaded events replaced.
        context.work_units = []
        for profile in context.agents.values():
            profile.allocated_work_ids = []
            profile.received_work_ids = []
    else:
        for unit in context.work_units:
            unit.intent_id = intent_id_map.get(unit.intent_id, unit.intent_id)
    context.flags = _load_records(payload.get("flags"), FlagEntry)
    context.delivery_span_index = _integer(payload.get("delivery_span_index"), -1)
    context.rebuild_runtime_indexes()
    return context, dict(payload)


def _load_records(value: Any, record_type: type) -> list[Any]:
    """Restore dataclass records, ignoring unknown keys and bad rows."""
    fields = getattr(record_type, "__dataclass_fields__", {})
    records: list[Any] = []
    for item in _items(value):
        try:
            records.append(
                record_type(**{key: item[key] for key in item if key in fields})
            )
        except TypeError:
            continue
    return records


def trajectory_context_to_payload(
    context: TrajectoryContext,
    *,
    schema_version: str,
    session_id: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Serialize a complete trajectory context without shortening its values."""
    payload: dict[str, Any] = {
        "schema_version": schema_version,
        "session_id": session_id,
        "policy_text": context.policy_text,
        "evidence": [_jsonable(item) for item in context.evidence],
        "intents": [_jsonable(item) for item in context.intents],
        "claims": [_jsonable(item) for item in context.claims],
        "coordination_events": [
            _jsonable(item) for item in context.coordination_events
        ],
        "provenance_links": [_jsonable(item) for item in context.provenance_links],
        "coordination_metadata": _jsonable(context.coordination_metadata),
        "final_answer_context": _jsonable(context.get_final_answer_context()),
        "coordination_context": _jsonable(context.coordination_context.to_payload()),
        "agents": [_jsonable(profile) for profile in context.agents.values()],
        "work_units": [_jsonable(unit) for unit in context.work_units],
        "flags": [_jsonable(flag) for flag in context.flags],
        "delivery_span_index": context.delivery_span_index,
    }
    if metadata:
        payload.update(_jsonable(dict(metadata)))
    return payload


def _items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _optional_integer(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _jsonable(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
