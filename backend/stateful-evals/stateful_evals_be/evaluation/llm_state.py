#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Store model-selected artifacts and exact source pointers after each span."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, fields
from typing import Any

from stateful_evals_be.evaluation.trajectory_context import (
    AgentProfile, ClaimEntry, CoordinationEvent, EvidenceFact, IntentEntry,
    TrajectoryContext, WorkUnit, _timestamp_ns,
)

_RECORDS = {
    "evidence": (EvidenceFact, "fact", "content"),
    "claims": (ClaimEntry, "claim", "content"),
    "intents": (IntentEntry, "intent", "description"),
    "agents": (AgentProfile, "agent", None),
    "work_units": (WorkUnit, "work", "request"),
    "coordination_events": (CoordinationEvent, "coordination", "content"),
}
_MUTABLE = {"intents", "agents", "work_units"}
_METADATA_REFS = {
    "policy_text_ref": "policy_text", "root_request_ref": "root_request",
    "final_answer_ref": "latest_root_answer", "tool_definitions_ref": "tool_definitions",
}
_ENVELOPE = {"span_id": "SpanId", "parent_span_id": "ParentSpanId", "trace_id": "TraceId"}
_AUTOMATIC = set(_ENVELOPE) | set(_ENVELOPE.values()) | {"span_index", "first_seen", "last_seen", "started_at_ns", "duration_ns", "request_span_index", "started_at", "ended_at", "Timestamp", "Duration"}


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


class LLMState:
    """The span loop owns one state; the model supplies its semantic updates."""

    def __init__(self, raw_spans: list[dict[str, Any]]) -> None:
        self._raw_spans = raw_spans
        self._catalogs: dict[int, list[dict[str, Any]]] = {}
        self._sources: dict[str, tuple[int, list[str | int], Any]] = {}
        self.context = TrajectoryContext(policy_text="", artifact_organization="llm")
        self.context.source_spans = []
        self.context.artifact_sources = {}

    @staticmethod
    def schema() -> dict[str, Any]:
        """Small prompt guide for the existing record constructors."""
        return {
            "instructions": (
                "Return state_delta with ledger lists directly at its top level: evidence, claims, "
                "intents, agents, work_units, coordination_events, plus operation and metadata. "
                "Do not nest these lists inside records or record_fields; do not output new_record_ids. "
                "operation is one object, never an operations list. Return only new/changed coarse "
                "records; empty lists are allowed. The record_fields guide below describes fields, "
                "not a wrapper to copy into the response. "
                "Every record, including agents, requires id and source_ref from the source catalog. "
                "For a NEW intent/work unit, source_ref selects its complete original request; "
                "description_ref/request_ref is only an optional replacement on later updates. "
                "Agent IDs can identify observed authors, owners, or recipients before an agent profile "
                "or contract appears. Add profiles when their attributes are observed. Use short labels. "
                "Creation slots use N, "
                "then N+1, N+2 for multiple new records in that ledger. Select the smallest "
                "complete response, request, contract, or tool result; do not select an entire "
                "span/conversation when its individual message is available. Never split responses "
                "into propositions or duplicate repeated history. Content is copied from source_ref. "
                "Only intents, agents, and work_units can update an existing ID; omit unchanged fields. "
                "An update's source_ref supports the change; description_ref/request_ref replaces "
                "the original request only when that request changed. Relationship IDs may reference "
                "existing or same-delta records; null means unknown, [] means no list relationship. "
                "Infer links from meaning, including which broader request a delegated task serves. "
                "evidence_refs can cite facts/contracts and claims from earlier spans; provenance "
                "does not make an agent's claim verified truth. Include one operation for the action "
                "actually recorded; proposed actions are not executions. Select operation input_ref "
                "only for current request/tool arguments, never a whole replayed conversation. Metadata refs are optional "
                "and unchanged when absent/null. Select final_answer_ref only for a root agent's "
                "actual user-facing response, and update it when a later root answer is recorded. "
                "All categories, roles, owners, statuses, and links are model decisions."
            ),
            "record_fields": {
                "evidence": "id=fact:N; source_ref; fact_type, source_name; optional agent_id, actor_scope, related_intent_ids, work_id, outcome, tool_call_id, relayed_from_agent_id",
                "claims": "id=claim:N; source_ref; claim_type, entity_name; agent_id, related_intent_ids; optional actor_scope, evidence_refs, revision_of_claim_id, work_id",
                "intents": "id=intent:N; source_ref; name, source, status=unassessed|in_progress|fulfilled|failed|blocked|superseded; owner_agent_ids, parent_intent_ids; optional requirement_type, assigned_by_agent_id, dependency_intent_ids, expected_output, description_ref",
                "agents": "id=stable agent ID; source_ref; optional contract_ids, declared_capability, declared_tools, active",
                "work_units": "id=work:N; source_ref; allocator_agent_id, recipient_agent_ids, intent_id; optional response_artifact_ids, response_span_index, outcome, request_ref",
                "coordination_events": "id=coordination:N; source_ref; event_type, operation_name; optional actor_agent_id, sender_agent_ids, recipient_agent_ids, related_intent_ids, input_artifact_ids, output_artifact_ids, status",
            },
            "operation": "operation_type=llm|tool|coordination, entity_name, actor_scope=root|peer|unknown, is_delegation; optional agent_id, content_ref, input_ref, evidence_refs, work_id, delegation_id, delegator_agent_id, recipient_agent_ids, outcome, coordination_event_ids",
            "metadata": "optional root_agent_id, policy_text_ref, root_request_ref, final_answer_ref, tool_definitions_ref, delivery_span_index, termination_span_index",
        }

    def source_catalog(self, span_index: int) -> list[dict[str, Any]]:
        """Assign stable IDs to structural nodes, including JSON-encoded objects."""
        if type(span_index) is not int or not 0 <= span_index < len(self._raw_spans):
            raise ValueError("Unknown source span")
        if span_index > len(self.context.source_spans):
            raise ValueError("Future source span is unavailable")
        if span_index not in self._catalogs:
            catalog = []

            def visit(value, path):
                source_id = f"source:{span_index}:{len(catalog)}"
                self._sources[source_id] = (span_index, path, value)
                preview = f"{len(value)} fields" if isinstance(value, dict) else f"{len(value)} items" if isinstance(value, list) else _text(value)[:80]
                catalog.append({"source_id": source_id, "location": path, "preview": preview})
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except json.JSONDecodeError:
                        return
                if isinstance(value, dict):
                    for key in sorted(value):
                        visit(value[key], [*path, key])
                elif isinstance(value, list):
                    for index, child in enumerate(value):
                        visit(child, [*path, index])

            visit(self._raw_spans[span_index], [])
            self._catalogs[span_index] = catalog
        return copy.deepcopy(self._catalogs[span_index])

    def _source_id(self, source_id):
        history = self.context.artifact_sources.get(source_id, []) if isinstance(source_id, str) else []
        return next((row["content_source_id"] for row in reversed(history) if "content_source_id" in row), source_id)

    def _source(self, source_id, span_index):
        source_id = self._source_id(source_id)
        if not isinstance(source_id, str) or source_id not in self._sources:
            raise ValueError(f"Unknown source_ref {source_id!r}; copy a catalog source_id")
        source_index, path, value = self._sources[source_id]
        if source_index > span_index:
            raise ValueError(f"Future source_ref {source_id!r}")
        return {"span_index": source_index, "path": path}, value

    def prompt_state(self) -> dict[str, Any]:
        """Send each selected source once; records and operations point to it."""
        ctx = self.context
        result = {"records": {}, "new_record_ids": {}, "selected_source_texts": {}}
        for name, (_, prefix, text_field) in _RECORDS.items():
            rows = list(ctx.agents.values()) if name == "agents" else getattr(ctx, name)
            result["records"][name] = []
            for index, row in enumerate(rows):
                artifact_id = row.agent_id if name == "agents" else f"{prefix}:{index}"
                record = {"id": artifact_id, **asdict(row)}
                provenance = ctx.artifact_sources.get(artifact_id, [])
                content_id = next((p["content_source_id"] for p in reversed(provenance) if "content_source_id" in p), None)
                if text_field and content_id:
                    record.pop(text_field, None)
                    record[f"{text_field}_ref"] = content_id
                    result["selected_source_texts"][content_id] = self._sources[content_id][2]
                result["records"][name].append(record)
            if name != "agents":
                result["new_record_ids"][name] = f"{prefix}:{len(rows)}"
        result["operations"] = [{key: value for key, value in row.items() if key not in {"content", "input_payload", "input_ref"}} for row in ctx.raw_spans]
        for operation in result["operations"]:
            if operation.get("content_ref"):
                source_id = operation["content_ref"]
                result["selected_source_texts"][source_id] = self._sources[source_id][2]
        result["metadata"] = {"root_agent_id": ctx.root_agent_id}
        for key, attribute in _METADATA_REFS.items():
            provenance = ctx.artifact_sources.get(f"metadata:{attribute}", [])
            if provenance:
                source_id = provenance[-1]["source_id"]
                result["metadata"][key] = source_id
                result["selected_source_texts"][source_id] = self._sources[source_id][2]
        return result

    def validate(self, delta, span_index, raw_span=None):
        return self.apply(delta, span_index, raw_span, commit=False)

    def apply(self, delta, span_index, raw_span=None, *, commit=True):
        """Validate a complete delta before changing any accepted state."""
        if type(span_index) is not int or span_index != len(self.context.source_spans):
            raise ValueError("State updates must follow span order exactly once")
        if raw_span is not None and raw_span != self._raw_spans[span_index]:
            raise ValueError("Current span differs from its registered source")
        if not isinstance(delta, dict) or set(delta) - set(_RECORDS) - {"operation", "metadata"}:
            raise ValueError("state_delta must contain record lists, operation, and metadata")
        candidate = copy.deepcopy(self.context)
        for name in _RECORDS:
            rows = delta.get(name, [])
            if not isinstance(rows, list):
                raise ValueError(f"{name} must be a list")
            seen = set()
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in seen:
                    raise ValueError(f"{name} requires distinct nonempty string IDs")
                seen.add(row["id"])
                self._record(candidate, name, row, span_index)
        operation = delta.get("operation")
        if not isinstance(operation, dict) or operation.get("operation_type") not in {"llm", "tool", "coordination"} or operation.get("actor_scope") not in {"root", "peer", "unknown"}:
            raise ValueError("operation requires operation_type and actor_scope")
        if not isinstance(operation.get("entity_name"), str) or type(operation.get("is_delegation")) is not bool:
            raise ValueError("operation requires entity_name and boolean is_delegation")
        operation = {key: ([] if key.endswith(("_ids", "_refs")) else "") if value is None else value for key, value in operation.items() if key not in _AUTOMATIC | {"artifact_id"}}
        for key, target in (("content_ref", "content"), ("input_ref", "input_payload")):
            source_id = operation.get(key)
            if source_id not in (None, ""):
                source_id = self._source_id(source_id)
                operation[key] = source_id
                _, value = self._source(source_id, span_index)
                operation[target] = _text(value) if target == "content" else value
        operation.update(artifact_id=f"operation:{span_index}", span_index=span_index)
        if isinstance(self._raw_spans[span_index].get("Timestamp"), str):
            operation["started_at"] = self._raw_spans[span_index]["Timestamp"]
        operation.update({key: str(self._raw_spans[span_index][source]) for key, source in _ENVELOPE.items() if source in self._raw_spans[span_index]})
        candidate.raw_spans.append(operation)
        candidate.source_spans.append(self._raw_spans[span_index])
        self._metadata(candidate, delta.get("metadata", {}), span_index)
        self._validate_refs(candidate)
        candidate.rebuild_runtime_indexes()
        if commit:
            self.context.__dict__.update(candidate.__dict__)
        return candidate

    def _record(self, ctx, name, row, span_index):
        record_type, prefix, text_field = _RECORDS[name]
        artifact_id = row["id"]
        records = getattr(ctx, name)
        index = len(records)
        existing = records.get(artifact_id) if name == "agents" else None
        if name != "agents":
            _, separator, number = artifact_id.partition(":")
            if separator != ":" or not number.isdecimal() or artifact_id != f"{prefix}:{int(number)}" or int(number) > len(records):
                raise ValueError(f"Invalid sequential {name} ID: {artifact_id}")
            index = int(number)
            existing = records[index] if index < len(records) else None
        if existing is not None and name not in _MUTABLE:
            raise ValueError(f"{artifact_id} is an immutable observation; append a new record")
        selector_keys = ("source_ref", "content_ref", "description_ref", "request_ref")
        source_id = next((row[key] for key in selector_keys if row.get(key) not in (None, "")), None)
        if source_id is None and existing is not None:
            source_id = f"source:{span_index}:0"
        source_id = self._source_id(source_id)
        source_ref, _ = self._source(source_id, span_index)
        values = asdict(existing) if existing is not None else {}
        changes = {key: value for key, value in row.items() if key not in {"id", *selector_keys} | _AUTOMATIC}
        replacement = row.get(f"{text_field}_ref") if text_field else None
        if text_field and text_field in changes:
            raise ValueError(f"{text_field} must be selected using source_ref")
        defaults = asdict(existing) if existing is not None else {field.name: field.default_factory() for field in fields(record_type) if callable(field.default_factory)}
        changes = {key: ([] if isinstance(defaults.get(key), list) or key.endswith(("_ids", "_refs")) else "") if value is None else value for key, value in changes.items()}
        values.update(changes)
        content_id = None
        if text_field and (existing is None or replacement):
            content_id = self._source_id(replacement or source_id)
            _, value = self._source(content_id, span_index)
            values[text_field] = _text(value)
        for key, value in values.items():
            if key in defaults and isinstance(defaults[key], list) and (not isinstance(value, list) or key != "events" and any(not isinstance(item, str) for item in value)):
                raise ValueError(f"{artifact_id}.{key} must be a list")
            if key in {"name", "source", "status", "fact_type", "source_name", "claim_type", "entity_name", "event_type", "operation_name", "allocator_agent_id"} and not isinstance(value, str):
                raise ValueError(f"{artifact_id}.{key} must be a string")
        if name == "intents" and values.get("status") not in {"unassessed", "in_progress", "fulfilled", "failed", "blocked", "superseded"}:
            raise ValueError("Invalid intent status")
        if "active" in values and type(values["active"]) is not bool:
            raise ValueError("Agent active must be boolean")
        field_names = {field.name for field in fields(record_type)}
        if "span_index" in field_names:
            values["span_index"] = source_ref["span_index"]
        if "first_seen" in field_names:
            values.setdefault("first_seen", span_index)
            values["last_seen"] = span_index
        if name == "work_units" and existing is None:
            values["request_span_index"] = source_ref["span_index"]
        identity = {"agents": "agent_id", "work_units": "work_id", "coordination_events": "event_id"}.get(name)
        if identity:
            if identity in changes and changes[identity] != artifact_id:
                raise ValueError(f"{identity} must match id")
            values[identity] = artifact_id
        envelope = self._raw_spans[source_ref["span_index"]]
        values.update({key: str(envelope[source]) for key, source in _ENVELOPE.items() if key in field_names and source in envelope})
        if "started_at_ns" in field_names:
            values.update(started_at_ns=_timestamp_ns(envelope.get("Timestamp")), duration_ns=envelope.get("Duration"))
        record = record_type(**values)
        if name == "agents":
            records[artifact_id] = record
        elif existing is None:
            records.append(record)
        else:
            records[index] = record
        provenance = {"source_ref": source_ref, "source_id": source_id, "observed_at_span_index": span_index}
        if content_id:
            provenance.update(content_source_id=content_id, content_source_ref=self._source(content_id, span_index)[0])
        ctx.artifact_sources.setdefault(artifact_id, []).append(provenance)

    def _metadata(self, ctx, metadata, span_index):
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be an object")
        # Store selected fields; derived indexes come from the selected source.
        allowed = set(_METADATA_REFS) | {"source_ref", "root_agent_id", "delivery_span_index", "termination_span_index"}
        metadata = {key: value for key, value in metadata.items() if key in allowed}
        if metadata.get("source_ref") not in (None, ""):
            self._source(metadata["source_ref"], span_index)
        for key, attribute in _METADATA_REFS.items():
            if metadata.get(key) in (None, ""):
                continue
            source_id = self._source_id(metadata[key])
            source_ref, value = self._source(source_id, span_index)
            if key == "final_answer_ref":
                ctx.latest_root_answer_span_index = source_ref["span_index"]
            setattr(ctx, attribute, value if key == "tool_definitions_ref" else _text(value))
            ctx.artifact_sources.setdefault(f"metadata:{attribute}", []).append({"source_ref": source_ref, "source_id": source_id, "observed_at_span_index": span_index})
        if "root_agent_id" in metadata:
            ctx.root_agent_id = metadata["root_agent_id"]
        for key in ("delivery_span_index", "termination_span_index"):
            if key in metadata:
                if type(metadata[key]) is not int or not 0 <= metadata[key] <= span_index:
                    raise ValueError(f"Invalid {key}")
                setattr(ctx, key, metadata[key])

    @staticmethod
    def _validate_refs(ctx):
        records = {f"{prefix}:{index}": asdict(row) for name, (_, prefix, _) in _RECORDS.items() if name != "agents" for index, row in enumerate(getattr(ctx, name))}
        records.update({key: asdict(row) for key, row in ctx.agents.items()})
        records.update({row["artifact_id"]: row for row in ctx.raw_spans})
        contracts = {fact.source_name for fact in ctx.evidence if fact.fact_type == "policy_rule"} | ({"policy:root"} if ctx.policy_text else set())
        for artifact_id, row in records.items():
            for key, value in row.items():
                if key.endswith(("_ids", "_refs")) and (not isinstance(value, list) or any(not isinstance(item, str) for item in value)):
                    raise ValueError(f"{artifact_id}.{key} must be a list of IDs")
                if key.endswith("span_index") and (type(value) is not int or not -1 <= value < len(ctx.source_spans)):
                    raise ValueError(f"{artifact_id}.{key} references an unavailable span")
                if not value or key in {"id", "agent_id", "work_id", "event_id"} and value == artifact_id:
                    continue
                targets = value if isinstance(value, list) else [value]
                family = "intent:" if key == "intent_id" or key.endswith("intent_ids") else "work:" if key in {"work_id", "retry_of_work_id", "allocated_work_ids", "received_work_ids"} else "claim:" if key == "revision_of_claim_id" else None
                relation = family or key.endswith(("agent_id", "agent_ids", "artifact_id", "artifact_ids")) or key in {"evidence_refs", "contract_ids", "coordination_event_ids"}
                if not relation:
                    continue
                for target in targets:
                    if key.endswith(("agent_id", "agent_ids")):
                        if not isinstance(target, str):
                            raise ValueError(f"{artifact_id}.{key} must contain agent IDs")
                        continue
                    if not isinstance(target, str) or target not in records and target not in contracts or family and not target.startswith(family):
                        raise ValueError(f"{artifact_id}.{key}: unavailable reference {target!r}")
                    if key == "evidence_refs" and not (target.startswith(("fact:", "claim:")) or target in contracts):
                        raise ValueError(f"{artifact_id}.evidence_refs must cite facts, contracts, or earlier claims")
                    if key == "evidence_refs" and target in records and records[target].get("span_index", -1) > row.get("span_index", len(ctx.source_spans)):
                        raise ValueError(f"{artifact_id} cannot cite future evidence")
                    if key == "evidence_refs" and target.startswith("claim:") and records[target]["span_index"] >= row.get("span_index", len(ctx.source_spans)):
                        raise ValueError(f"{artifact_id} can cite only claims from earlier spans")
        if not isinstance(ctx.root_agent_id, str):
            raise ValueError("root_agent_id must be a string")
