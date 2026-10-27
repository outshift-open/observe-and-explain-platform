"""Local, provenance-first retrieval for a single span judgment.

The budget applies to optional retrieval, never to stored artifacts or directly
referenced evidence. An expanded view provides a bounded second judgment when
the initial selection cannot support a decision.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from stateful_evals_be.evaluation.reasoning_graph import source_quotation_text

if TYPE_CHECKING:
    from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def recorded_operation_carriers(context: TrajectoryContext) -> list[dict[str, Any]]:
    """Expose native operation provenance without relabelling model-owned records."""
    from stateful_evals_be.evaluation.llm_state import LLMState

    spans = getattr(context, "source_spans", [])
    if not spans or getattr(context, "artifact_organization", "") != "llm":
        return []
    state = LLMState(spans)
    state.context = context
    result = []
    for operation in context.raw_spans:
        index = operation.get("span_index")
        if type(index) is not int or not 0 <= index < len(spans):
            continue
        raw = spans[index]
        attrs = raw.get("SpanAttributes", {})
        carrier = {
            "operation_id": operation.get("artifact_id", f"operation:{index}"),
            "span_index": index,
            "recorded_envelope": {key: raw[key] for key in (
                "SpanId", "ParentSpanId", "TraceId", "SpanName", "Timestamp", "Duration", "StatusCode"
            ) if key in raw},
            "recorded_attributes": {key: attrs[key] for key in (
                "mas.boundary", "traceloop.span.kind", "ioa_observe.span.kind",
                "mas.call.id", "mas.parent.call.id", "tool.name",
                "traceloop.entity.name", "ioa_observe.entity.name",
                "mas.status", "mas.observation.complete", "mas.observation.timestamp"
            ) if isinstance(attrs, dict) and key in attrs},
            "selected_sources": {},
        }
        for field in ("input_ref", "content_ref"):
            source_id = operation.get(field)
            if not source_id:
                continue
            source = {"source_id": source_id}
            try:
                resolved_id = state._source_id(source_id)
                parts = resolved_id.split(":")
                source_index = int(parts[1]) if len(parts) == 3 and parts[0] == "source" else -1
                if 0 <= source_index <= index:
                    state.source_catalog(source_index)
                location, value = state._source(resolved_id, index)
                annotation = state._sources[resolved_id][3]
                if resolved_id != source_id:
                    source["resolved_source_id"] = resolved_id
                source.update(source_ref=location, **{key: annotation[key] for key in (
                    "direction", "message_role", "agent_id"
                ) if key in annotation})
                text = source_quotation_text(value)
                source.update(artifact_id=resolved_id, content=text, quotation_text=text,
                              span_index=location["span_index"], kind="source")
            except (ValueError, TypeError, AttributeError):
                source["status"] = "unresolved_at_operation_span"
            carrier["selected_sources"][field] = source
        result.append(carrier)
    return result


def current_agent_instruction_records(span: dict[str, Any]) -> list[dict[str, Any]]:
    """Retain full current contracts with recorded ownership in either judge mode."""
    from stateful_evals_be.evaluation.trajectory_context import _extract_prompt_messages

    payload = span.get("input_payload") or {}
    if not isinstance(payload, dict):
        return []
    source = {
        "kind": "current_agent_instruction",
        "agent_id": span.get("agent_id") or None,
        "span_id": str(span.get("span_id") or ""),
    }
    texts = [
        (message["content"], "system_message")
        for message in _extract_prompt_messages(payload)
        if message["role"] == "system"
    ]
    texts.extend(
        (payload[key], "system_message")
        for key in ("system_prompt", "system_message")
        if isinstance(payload.get(key), str)
    )
    contract = payload.get("agent_contract")
    if isinstance(contract, dict):
        texts.append(
            (
                "Agent contract: "
                + json.dumps(contract, ensure_ascii=False, sort_keys=True, default=str),
                "agent_contract",
            )
        )
    records: dict[str, dict[str, Any]] = {}
    for content, source_name in texts:
        if not content:
            continue
        record = records.setdefault(
            content.strip(), {"content": content, "sources": []}
        )
        origin = {**source, "source_name": source_name}
        if origin not in record["sources"]:
            record["sources"].append(origin)
    return list(records.values())


def _identifier_fields(value: Any, *, arguments: bool = False) -> set[str]:
    """Find record-reference fields in structured tool arguments."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return set()
    if isinstance(value, list):
        return set().union(*(_identifier_fields(v, arguments=arguments) for v in value))
    if not isinstance(value, dict):
        return set()
    fields = set()
    for key, child in value.items():
        if arguments and (key in {"id", "ids"} or key.endswith(("_id", "_ids"))):
            fields.add(key)
        fields.update(
            _identifier_fields(child, arguments=arguments or key == "arguments")
        )
    return fields


def _field_values(value: Any, field: str) -> list[Any]:
    """Read exact values from structured payloads, including JSON content strings."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    if isinstance(value, list):
        return [v for child in value for v in _field_values(child, field)]
    if not isinstance(value, dict):
        return []
    values = []
    for key, child in value.items():
        if key == field:
            candidates = child if isinstance(child, list) else [child]
            values.extend(v for v in candidates if isinstance(v, (str, int, float)))
        else:
            values.extend(_field_values(child, field))
    return list(dict.fromkeys(values))


def _available(context: TrajectoryContext, item: Any, index: int, now: str) -> bool:
    from stateful_evals_be.evaluation.trajectory_context import _timestamp_ns

    if item.span_index >= index:
        return False
    if item.span_id:
        source = context._processed_spans.get(item.span_id)
        if source is None:
            return False  # Adapter sidecars may describe future operations.
        started = _timestamp_ns(source.get("timestamp"))
        current = _timestamp_ns(now)
        if started is not None and current is not None:
            # A span that ends after the current one starts is not yet evidence.
            if started + (source.get("duration_ns") or 0) > current:
                return False
    return True


def _tool_reference(source: dict[str, Any], content: str) -> tuple[Any, str]:
    """Read response values only; no reported error does not establish success."""
    output = source.get("tool_output", content)
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except ValueError:
            output = None
    failed = bool(source.get("contains_error"))
    if isinstance(output, dict):
        failed |= bool(output.get("error")) or output.get("isError") is True
        failed |= output.get("is_error") is True
        failed |= any(
            str(output.get(key, "")).casefold() in {"error", "failed", "failure"}
            for key in ("status", "outcome", "result_status")
        )
    return output, "error" if failed else "unknown"


def select_span_context(
    context: TrajectoryContext,
    span: dict[str, Any],
    *,
    span_index: int,
    max_chars: int,
    expanded: bool = False,
) -> dict[str, Any]:
    from stateful_evals_be.evaluation.trajectory_context import (
        _extract_agent_output,
        _extract_prompt_messages,
        _span_agent_id,
        _span_links,
    )

    agent = _span_agent_id(span)
    now = str(span.get("timestamp") or "")
    messages = _extract_prompt_messages(span.get("input_payload") or {})
    recent = [m for m in messages if m["role"] != "system"][-2:]
    call_payload = (
        span.get("input_payload")
        if span.get("entity_type") == "tool"
        else _extract_agent_output(span.get("output_payload") or {})
    )
    identifiers = _identifier_fields(
        call_payload, arguments=span.get("entity_type") == "tool"
    )
    roots = [m["content"] for m in messages if m["role"] in {"user", "human"}][:1]
    budget_policies = [m["content"] for m in messages if m["role"] == "system"]
    # Keep ownership with each instruction without repeating shared contracts.
    # Use recorded identity here; the retrieval agent may be a service fallback.
    instructions: dict[str, dict[str, Any]] = {}

    def add_instruction(content: str, source: dict[str, Any]) -> None:
        if not content:
            return
        record = instructions.setdefault(
            content.strip(), {"content": content, "sources": []}
        )
        if source not in record["sources"]:
            record["sources"].append(source)

    add_instruction(context.policy_text, {"kind": "root_policy"})
    for record in current_agent_instruction_records(span):
        for source in record["sources"]:
            add_instruction(record["content"], source)
    if expanded:
        for i, fact in enumerate(context.evidence):
            if fact.fact_type == "policy_rule" and fact.span_index < span_index:
                budget_policies.append(fact.content)
                add_instruction(
                    fact.content,
                    {
                        "kind": "prior_agent_instruction",
                        "agent_id": fact.agent_id or None,
                        "artifact_id": context._evidence_artifact_id(i, fact),
                        "source_name": fact.source_name,
                    },
                )
    budget_policies = list(dict.fromkeys([context.policy_text, *budget_policies]))
    budget_policies = [text for text in budget_policies if text]

    facts = {
        context._evidence_artifact_id(i, f): f
        for i, f in enumerate(context.evidence)
        if f.fact_type != "policy_rule" and _available(context, f, span_index, now)
    }
    claims = {
        f"claim:{i}": c
        for i, c in enumerate(context.claims)
        if _available(context, c, span_index, now)
    }
    events = {
        e.event_id: e
        for e in context.coordination_events
        if _available(context, e, span_index, now)
    }
    artifacts = {**facts, **claims, **events}
    # Exact message matches and explicit span links are the strongest signal;
    # they also find old evidence outside a recency window.
    direct = set(context._input_artifact_ids({"messages": recent})) & artifacts.keys()
    for link in _span_links(span):
        direct.update(
            set(context._span_artifact_ids.get(link["span_id"], [])) & artifacts.keys()
        )
    parent = str(span.get("parent_span_id") or "")
    direct.update(set(context._span_artifact_ids.get(parent, [])) & artifacts.keys())
    # Identifier-bearing calls need the actual reference records: tool outputs
    # with the same structured field, records holding a requested value (not
    # merely echoing it) first, then the most recent.
    argument_evidence = []
    for field in sorted(identifiers):
        requested = _field_values(call_payload, field)
        candidates = []
        references = {}
        for artifact_id, fact in facts.items():
            if fact.fact_type != "tool_output":
                continue
            source = context._processed_spans.get(fact.span_id, {})
            output, outcome = _tool_reference(source, fact.content)
            values = _field_values(output, field)
            if not values:
                continue
            input_values = _field_values(source.get("tool_input"), field)
            echoed = [v for v in values if v in input_values]
            holds_requested = any(v in requested and v not in echoed for v in values)
            candidates.append((holds_requested, fact.span_index, artifact_id))
            references[artifact_id] = {
                "field": field,
                "requested_values": requested,
                "observed_values": values,
                "source_outcome": outcome,
                "echoed_request_values": echoed,
                "artifact_id": artifact_id,
            }
        # Keep recent errors as negative evidence without displacing the records
        # needed to check the requested identifiers.
        remaining = {"unknown": 2, "error": 1}
        for _, _, artifact_id in sorted(candidates, reverse=True):
            reference = references[artifact_id]
            outcome = reference["source_outcome"]
            if remaining[outcome]:
                remaining[outcome] -= 1
                direct.add(artifact_id)
                argument_evidence.append(reference)

    # "Same work" is the intent of the span's own work unit plus the exact
    # intent ids of its direct artifacts, so a span reading a delegation result
    # ranks that delegation's records. Parents/dependencies only widen the view.
    work_ids = set(context._scope_intent_ids(span, span_index=span_index))
    for artifact_id in direct:
        work_ids.update(artifacts[artifact_id].related_intent_ids)
    intent_ids = set(work_ids)
    pending = list(intent_ids)
    while pending:
        intent = context._intent_by_artifact_id(pending.pop())
        if intent is None:
            continue
        for related in intent.parent_intent_ids + intent.dependency_intent_ids:
            if related not in intent_ids:
                intent_ids.add(related)
                pending.append(related)

    # Keep the root requirements visible, but omit their repeated event payloads.
    intents = []
    for i, intent in enumerate(context.intents):
        if intent.first_seen >= span_index:
            continue
        if f"intent:{i}" not in intent_ids and intent.source == "agent_plan":
            continue
        intents.append(
            {
                "artifact_id": f"intent:{i}",
                "requirement": intent.description or intent.name,
                "source": intent.source,
                "owners": intent.owner_agent_ids,
                "status": intent.status if intent.last_seen < span_index else "unknown",
                "expected_output": intent.expected_output,
                "dependencies": intent.dependency_intent_ids,
            }
        )

    view: dict[str, Any] = {
        "intents": intents,
        "instructions": list(instructions.values()),
        "current_request": roots,
        "facts": [],
        "recent_claims": [],
        "recent_coordination_events": [],
        "argument_evidence": argument_evidence,
    }
    included: set[str] = set()
    seen_content: dict[str, dict[str, Any]] = {}
    # Instruction provenance and newly exposed full contracts are mandatory
    # overhead; they must not evict evidence that fit the prior text-only budget.
    used = _size({**view, "instructions": budget_policies})
    # Rank by structure only: same work item, then the agent's own artifacts and
    # coordination edges it sent or received, then recency.
    ranked = []
    for artifact_id, item in artifacts.items():
        same_work = bool(work_ids.intersection(item.related_intent_ids))
        if artifact_id in events:
            parties = {
                item.actor_agent_id,
                *item.sender_agent_ids,
                *item.recipient_agent_ids,
            }
        else:
            parties = {item.agent_id}
        tier = 2 * same_work + bool(agent and agent in parties)
        if artifact_id in direct or tier or expanded:
            ranked.append((artifact_id in direct, tier, item.span_index, artifact_id))
    ranked.sort(reverse=True)

    def include(artifact_id: str, required: bool = False) -> None:
        nonlocal used
        if artifact_id in included or artifact_id not in artifacts:
            return
        item = artifacts[artifact_id]
        # A tool-result claim is another view of its canonical fact.
        if artifact_id in claims and item.claim_type == "tool_result":
            refs = [r for r in item.evidence_refs if r in facts]
            if refs:
                for ref in refs:
                    include(ref, required)
                if all(ref in included for ref in refs):
                    included.add(artifact_id)
                    for ref in refs:
                        for record in view["facts"]:
                            if record["artifact_id"] == ref:
                                record.setdefault("alias_ids", []).append(artifact_id)
                    return
        if artifact_id in events:
            record = {
                "artifact_id": artifact_id,
                "event_type": item.event_type,
                "span_id": item.span_id,
                "sender_ids": item.sender_agent_ids,
                "recipient_ids": item.recipient_agent_ids,
                "input_artifact_ids": item.input_artifact_ids,
                "output_artifact_ids": item.output_artifact_ids,
            }
            component = "recent_coordination_events"
        else:
            record = {
                "artifact_id": artifact_id,
                "span_id": item.span_id,
                "agent_id": item.agent_id,
                "content": item.content,
                "kind": item.fact_type if artifact_id in facts else item.claim_type,
            }
            if artifact_id in claims:
                record["evidence_refs"] = list(item.evidence_refs)
                record["revision_of_claim_id"] = item.revision_of_claim_id
            component = "facts" if artifact_id in facts else "recent_claims"
            key = record["kind"] + ":" + " ".join(item.content.split())
            if artifact_id in claims:
                key += json.dumps([item.evidence_refs, item.revision_of_claim_id])
            if key in seen_content:
                seen_content[key].setdefault("alias_ids", []).append(artifact_id)
                included.add(artifact_id)
                include_sources(artifact_id)
                return
        cost = _size(record)
        if not (required or expanded) and used + cost > max_chars:
            return
        view[component].append(record)
        included.add(artifact_id)
        used += cost
        if artifact_id not in events:
            seen_content[key] = record
        include_sources(artifact_id)

    def include_sources(artifact_id: str) -> None:
        # Follow provenance for every selected claim, including ranked claims
        # forwarded by another agent. Availability filtering still applies.
        item = claims.get(artifact_id)
        if item:
            for ref in [*item.evidence_refs, item.revision_of_claim_id]:
                if ref in facts or ref in claims:
                    include(ref, required=True)

    for artifact_id in sorted(direct):
        include(artifact_id, required=True)
    for _, _, _, artifact_id in ranked:
        include(artifact_id)
    view["selection"] = {
        "mode": "expanded" if expanded else "focused",
        "omitted_artifacts": len(artifacts.keys() - included),
        "soft_budget_exceeded": _size(view) > max_chars,
    }
    return view


# The model-owned span pipeline uses these views. Stored state and source IDs
# remain unchanged; archive navigation is explicitly distinct from evidence.
def _source_refs(value: Any) -> set[str]:
    if isinstance(value, list):
        return set().union(*(_source_refs(v) for v in value), set())
    if not isinstance(value, dict):
        return set()
    fields = {"source_id", "content_source_id", "source_ref", "content_ref", "input_ref",
              "request_ref", "description_ref", "policy_text_ref", "root_request_ref",
              "final_answer_ref", "tool_definitions_ref", "source_ids", "omitted_source_ids"}
    candidates = [item for key in fields for item in
                  (value.get(key, []) if isinstance(value.get(key), list) else [value.get(key)])]
    return {item for item in candidates if isinstance(item, str) and item.startswith("source:")} | _source_refs(value.get("anchors", []))


def _archive_records(prior: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = {r["id"]: r for rows in prior.get("records", {}).values() for r in rows}
    records.update({r["id"]: r for rows in prior.get("reasoning_graph", {}).values() for r in rows})
    records.update({r["artifact_id"]: r for r in prior.get("operations", [])})
    return records


def _source_key(value: Any) -> str:
    import hashlib
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _source_bound(state: Any, span_index: int | None) -> int:
    accepted = len(state.context.source_spans)
    if span_index is None:
        return accepted - 1
    if type(span_index) is not int or not 0 <= span_index <= accepted:
        raise ValueError("Context expansion cannot observe a future span")
    return span_index


def expand_context(state: Any, prior: dict[str, Any], refs: list[str], *,
                   span_index: int | None = None) -> dict[str, Any]:
    """Resolve exact IDs within this state and cutoff; never search other cases."""
    from copy import deepcopy
    limit = _source_bound(state, span_index)
    records = _archive_records(prior)
    result: dict[str, Any] = {"sources": {}, "records": {}, "spans": {}, "source_catalog": {}, "unavailable_refs": []}
    if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
        raise ValueError("context_requests must be a list of exact ID strings")
    pending = list(dict.fromkeys(refs))
    seen = set()
    while pending:
        ref = pending.pop(0)
        if ref in seen:
            continue
        seen.add(ref)
        try:
            if ref.startswith("source:"):
                location, value = state._source(ref, limit)
                result["sources"][ref] = {"source_id": ref, "source_ref": location,
                                          "quotation_text": source_quotation_text(value)}
                index, path = location["span_index"], location["path"]
            elif ref.startswith("span:"):
                index = int(ref.split(":", 1)[1])
                if not 0 <= index <= limit or index >= len(state._raw_spans):
                    raise ValueError("Unavailable source span")
                sid = next(item["source_id"] for item in state.source_catalog(index) if not item["location"])
                result["spans"][ref] = {"source_id": sid,
                                        "quotation_text": source_quotation_text(state._raw_spans[index])}
                path = []
            elif ref in records:
                record = records[ref]
                if max(record.get("span_index", -1), record.get("last_seen", -1)) > limit:
                    raise ValueError("Unavailable future record")
                result["records"][ref] = deepcopy(record)
                pending.extend(sorted(_source_refs(record)))
                continue
            else:
                raise ValueError("Unknown archive ID")
            for item in state.source_catalog(index):
                if item["location"][:len(path)] == path:
                    sid = item["source_id"]
                    result["source_catalog"][sid] = {"location": item["location"], **state._sources[sid][3]}
        except (ValueError, KeyError, IndexError):
            result["unavailable_refs"].append(ref)
    return result


def _visible_sources(state: Any, refs: set[str], limit: int) -> tuple[dict, dict]:
    """Represent identical bodies and parent/child selections only once."""
    sources, aliases, fingerprints, locations = {}, {}, {}, {}
    for ref in sorted(refs, key=lambda r: (len(state._sources.get(r, (0, [], None, {}))[1]), r)):
        location, value = state._source(ref, limit)
        parent = next((other for other, where in locations.items()
                       if location["span_index"] == where["span_index"]
                       and location["path"][:len(where["path"])] == where["path"]), None)
        if parent:
            aliases[ref] = {"source_id": parent, "path": location["path"][len(locations[parent]["path"]):]}
            continue
        key = _source_key(value)
        if key in fingerprints:
            aliases[ref] = {"source_id": fingerprints[key], "path": []}
        else:
            sources[ref], locations[ref], fingerprints[key] = value, location, ref
    # Long descendants are already readable inside a pinned parent. Describe
    # their location rather than copying their text again in the current view.
    for ref, (index, path, value, _) in state._sources.items():
        if index <= limit and ref not in sources and ref not in aliases and _size(value) >= 128:
            parent = next((other for other, where in locations.items() if index == where["span_index"]
                           and path[:len(where["path"])] == where["path"]), None)
            if parent:
                aliases[ref] = {"source_id": parent, "path": path[len(locations[parent]["path"]):]}
    return sources, aliases


def _message_sources(state: Any, limit: int, roles: set[str], *, input_only: bool = True) -> tuple[set[str], list[dict]]:
    """Select complete bodies at recorded message boundaries, never quoted roles."""
    refs, occurrences = set(), []
    paths = {(index, tuple(path)): (sid, annotation) for sid, (index, path, _, annotation)
             in state._sources.items() if index <= limit}
    for sid, (index, path, value, annotation) in state._sources.items():
        if index > limit or annotation.get("message_role") not in roles or input_only and annotation.get("direction") == "output":
            continue
        field = path[-1] if path else ""
        if isinstance(field, str) and field.startswith(("gen_ai.prompt.", "gen_ai.completion.")) and not field.endswith((".content", ".parts")):
            continue
        parent = paths.get((index, tuple(path[:-1])))
        if parent and parent[1].get("message_role") == annotation["message_role"]:
            continue
        # Preserve the complete recorded instruction body, with its observed
        # message/recipient identity beside it. No instruction text is classified.
        parsed = value
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except ValueError:
                pass
        flat_body = isinstance(field, str) and field.startswith(("gen_ai.prompt.", "gen_ai.completion."))
        body = next((paths[(index, tuple([*path, key]))][0] for key in ("content", "parts")
                     if not flat_body and isinstance(parsed, dict) and key in parsed and (index, tuple([*path, key])) in paths), sid)
        refs.add(body)
        occurrences.append({"source_id": body, "message_source_id": sid, "span_index": index,
                            **{k: annotation[k] for k in ("message_role", "agent_id", "direction") if k in annotation}})
    return refs, occurrences


def _instruction_sources(state: Any, limit: int) -> tuple[set[str], list[dict]]:
    return _message_sources(state, limit, {"system", "developer"})


def _navigation(record: dict[str, Any]) -> dict[str, Any]:
    keep = {"id", "artifact_id", "type", "parent_id", "artifact_ref", "span_index", "first_seen", "last_seen",
            "agent_id", "owner_agent_ids", "sender_agent_ids", "recipient_agent_ids", "intent_id",
            "parent_intent_ids", "related_intent_ids", "from_id", "to_id", "relation", "task_id",
            "proposition_ids", "state_ids", "target_ids", "supersedes", "qualification", "outcome", "status"}
    result = {k: v for k, v in record.items() if k in keep and v not in (None, "", [], {})}
    label = next((record[k] for k in ("text", "name", "entity_name", "subject", "operation_name")
                  if isinstance(record.get(k), str) and record[k]), "")
    if label:
        result["navigation_label"] = label[:120]
    result["source_ids"] = sorted(_source_refs(record))
    result["view"] = "navigation_only_expand_ID_for_full_record_and_sources"
    return result


def _working_record(record: dict[str, Any]) -> dict[str, Any]:
    return {**{k: v for k, v in record.items() if k != "anchors"},
            "source_ids": sorted(_source_refs(record)), "view": "record_without_source_quotations"}


def build_span_view(state: Any, span_index: int, raw_span: dict[str, Any],
                    prior: dict[str, Any], metric_name: str) -> dict[str, Any]:
    """Project current observations and compact prior state without changing either."""
    _source_bound(state, span_index)
    if raw_span != state._raw_spans[span_index]:
        raise ValueError("Current observation differs from its registered source")
    catalog = state.source_catalog(span_index)
    refs, instructions = _instruction_sources(state, span_index)
    metadata, ledgers = prior.get("metadata", {}), prior.get("records", {})
    refs.update(v for k, v in metadata.items() if k in {"policy_text_ref", "root_request_ref"} and v)
    for record in ledgers.get("intents", []):
        refs.update(_source_refs(record))
    for record in ledgers.get("evidence", []):
        if record.get("fact_type") == "policy_rule":
            refs.update(_source_refs(record))
    graph = prior.get("reasoning_graph", {})
    for record in graph.get("nodes", []):
        if record.get("type") in {"SystemPrompt", "Constraint"}:
            refs.update(_source_refs(record))
    visible, visible_aliases = _visible_sources(state, refs, span_index)
    prior_values = {}
    for sid, (index, _, value, _) in state._sources.items():
        if index < span_index and _size(value) >= 128:
            prior_values.setdefault(_source_key(value), sid)
    seen = {**prior_values, **{_source_key(v): sid for sid, v in visible.items()},
            **{_source_key(state._sources[sid][2]): sid for sid in visible_aliases}}
    current_ids = {tuple(item["location"]): item["source_id"] for item in catalog}
    aliases, hidden_paths, visited = {}, [], set()

    def current(value: Any, path: list, *, register: bool = True) -> Any:
        visited.add(tuple(path))
        sid = current_ids.get(tuple(path))
        if register and sid and _size(value) >= 128:
            key = _source_key(value)
            if key in seen:
                target = seen[key]
                archived = target not in visible and target not in visible_aliases and state._sources[target][0] < span_index
                aliases[sid] = target
                if archived:
                    hidden_paths.append(path)
                return {"source_id": sid, "value_ref": target,
                        "view": "archive_reference_request_before_using" if archived else
                                "visible_source_alias" if target in visible or target in visible_aliases else "current_projection_alias"}
            seen[key] = sid
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except ValueError:
                decoded = None
            if isinstance(decoded, (dict, list)):
                return {"source_id": sid, "decoded_structure": current(decoded, path, register=False),
                        "view": "navigation_only_request_original_before_quoting_container"}
        if isinstance(value, dict):
            return {key: current(child, [*path, key]) for key, child in value.items()}
        if isinstance(value, list):
            return [current(child, [*path, index]) for index, child in enumerate(value)]
        return {"source_id": sid, "quotation_text": source_quotation_text(value)} if sid else value

    observation = current(raw_span, [])
    sources = [{**{k: v for k, v in item.items() if k != "preview"}, "view": "source_navigation_only",
                **({"content_status": "archived_request_before_using"} if any(
                    item["location"][:len(path)] == path for path in hidden_paths) else {})}
               for item in catalog if tuple(item["location"]) in visited
               or any(key in item for key in ("message_role", "direction", "agent_id"))]
    nodes = graph.get("nodes", [])
    required = {r["id"] for r in nodes if r.get("type") in {"Actor", "Intent", "Task", "Constraint", "SystemPrompt"}}
    working_graph = {"nodes": [_working_record(r) for r in nodes if r["id"] in required or r in nodes[-8:]],
                     "edges": [_working_record(r) for r in graph.get("edges", [])[-8:]]}
    for name in ("state_values", "checks"):
        rows = graph.get(name, [])
        superseded = {ref for r in rows for ref in r.get("supersedes", [])}
        selected = [r for r in rows if r["id"] not in superseded and (
            name == "state_values" or r.get("outcome") in {"pending", "unknown", "violated"} or r in rows[-8:])]
        working_graph[name] = [_working_record(r) for r in selected]
    working = {name: rows if name in {"intents", "agents", "work_units"} else rows[-6:]
               for name, rows in ledgers.items()}
    working_ids = {r["id"] for rows in working.values() for r in rows}
    graph_ids = {r["id"] for rows in working_graph.values() for r in rows}
    return {"current_span_index": span_index,
            "current_raw_span": {"span_ref": f"span:{span_index}", "source_projection": observation,
                                  "source_aliases": aliases},
            "available_current_sources": sources,
            "trajectory_state_before_span": {
                "records": working, "new_record_ids": prior.get("new_record_ids", {}),
                "artifact_index": {name: [_navigation(r) for r in rows if r["id"] not in working_ids]
                                   for name, rows in ledgers.items()},
                "operations": [_navigation(r) for r in prior.get("operations", [])], "metadata": metadata,
                "reasoning_graph": working_graph,
                "graph_index": {name: [_navigation(r) for r in rows if r["id"] not in graph_ids]
                                for name, rows in graph.items()},
                "selected_source_texts": {sid: {"source_id": sid, "quotation_text": source_quotation_text(value)}
                                          for sid, value in visible.items()},
                "source_aliases": visible_aliases,
                "instruction_occurrences": instructions, "context_view": metric_name},
            "archive_access": {
                "request_field": "context_requests", "reference_formats": ["source:span:node", "artifact ID", "span:index"],
                "cutoff_span_index": span_index,
                "instructions": "Navigation labels are not evidence. Archive references hide full bodies, not observed receipt events. "
                "Copy source_id and quotation_text together. Decoded containers and source paths are navigation; request "
                "the original source before quoting a container without quotation_text. Identical-value aliases reuse the "
                "same quotation text while retaining their recorded source identity; descendant paths require their own "
                "source text before quoting. All instructions remain attributed to their "
                "recorded agents. Request exact missing records or sources before relying on their contents."}}
