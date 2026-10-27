"""Local, provenance-first retrieval for a single span judgment.

The budget applies to optional retrieval, never to stored artifacts or directly
referenced evidence. An expanded view provides a bounded second judgment when
the initial selection cannot support a decision.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext


def _size(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


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
