# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""Typed span responses; JSON strings are limited to arbitrary-value fields."""

from copy import deepcopy
from dataclasses import fields
import json
from typing import get_args, get_origin, get_type_hints

from stateful_evals_be.evaluation import reasoning_graph
from stateful_evals_be.evaluation.trajectory_context import (
    AgentProfile, ClaimEntry, CoordinationEvent, EvidenceFact, IntentEntry, WorkUnit,
)

_STRING = {"type": "string"}
_INTEGER = {"type": "integer"}
_IDS = {"type": "array", "items": _STRING}
_JSON = {"type": "string", "description": "A JSON-encoded value, not prose."}
_JSON_OBJECT = {"type": "string", "description": "A JSON-encoded object, e.g. {}."}
_AUTO = {
    "span_index", "first_seen", "last_seen", "span_id", "parent_span_id", "trace_id",
    "started_at_ns", "duration_ns", "request_span_index",
}
_RECORDS = {
    "evidence": (EvidenceFact, "content", None),
    "claims": (ClaimEntry, "content", None),
    "intents": (IntentEntry, "description", None),
    "agents": (AgentProfile, None, "agent_id"),
    "work_units": (WorkUnit, "request", "work_id"),
    "coordination_events": (CoordinationEvent, "content", "event_id"),
}


def _object(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def _nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def _record(properties, required=("id",)):
    optional = [key for key in properties if key not in required]
    result = {key: value if key in required else _nullable(value)
              for key, value in properties.items()}
    if optional:
        result["clear_fields"] = {
            "type": "array", "items": {"type": "string", "enum": optional},
            "description": "Usually []. Null omits a field; list its name here only to explicitly clear it. Removed before storage.",
        }
    return _object(result)


def _field_schema(annotation):
    origin, args = get_origin(annotation), get_args(annotation)
    if type(None) in args:
        return _field_schema(next(arg for arg in args if arg is not type(None)))
    if origin is list:
        if len(args) == 1 and args[0] in (str, int, bool):
            return {"type": "array", "items": _field_schema(args[0])}
        return {"type": "string", "description": "A JSON-encoded array, e.g. []."}
    return {str: _STRING, int: _INTEGER, bool: {"type": "boolean"}}.get(annotation, _JSON)


def _coarse_schema(name, record_type, text_field, identity):
    hints = get_type_hints(record_type)
    properties = {"id": _STRING, "source_ref": _STRING}
    properties.update({field.name: _field_schema(hints[field.name])
                       for field in fields(record_type)
                       if field.name not in _AUTO | {text_field, identity}})
    properties.update({key: _STRING for key in
                       ("content_ref", "description_ref", "request_ref")})
    required = ["id"]
    if name not in {"intents", "agents", "work_units"}:
        required += ["source_ref"]
        required += {"evidence": ["fact_type", "source_name"],
                     "claims": ["claim_type", "entity_name"],
                     "coordination_events": ["event_type", "operation_name"]}[name]
    return _record(properties, required)


def _graph_schema():
    anchor = _object({"source_id": _STRING, "quote": {**_STRING, "description": "Verbatim source text. Prefer a leaf source; projected JSON structure is not its original serialization. Retrieve exact source if needed."},
                      "occurrence": {"type": "integer", "minimum": 0}})
    common = {"id": _STRING, "properties": _JSON_OBJECT,
              "anchors": {"type": "array", "items": anchor}}
    records = {
        "nodes": _record({**common, "type": {"type": "string", "enum": sorted(reasoning_graph.NODE_TYPES)},
                          "text": _STRING, "artifact_ref": _STRING,
                          "parent_id": {**_STRING, "description": "Required for Proposition: source-bearing Claim/Evidence/Intent/Task/ToolResult/SystemPrompt/Constraint node ID; never Actor or Proposition. Declare a compatible source parent in this delta when needed."}},
                         ("id", "anchors")),
        "edges": _record({**common, "from_id": _STRING, "to_id": _STRING,
                          "relation": _STRING, "basis": {"type": "string", "enum": ["recorded", "semantic", "assessment"]},
                          "reasoning": _STRING},
                         ("id", "anchors", "from_id", "to_id", "relation", "basis", "reasoning")),
        "state_values": _record({**common, "task_id": {**_STRING, "description": "ontology: ID of a Task node, never a coarse intent or other node type."}, "subject": _STRING,
                                 "property": _STRING, "value": {**_JSON, "description": 'A JSON-encoded value; use "null" for an unknown value.'},
                                 "unit": _STRING, "qualification": {"type": "string", "enum": ["observed", "reported", "estimated", "proposed", "derived", "unknown"]},
                                 "proposition_ids": {**_IDS, "minItems": 1, "description": "ontology: IDs of Proposition nodes declared previously or in this delta. Declare a source-backed Proposition before referencing it; Evidence/ToolResult nodes are not propositions."}, "supersedes": _IDS},
                                ("id", "anchors", "subject", "property", "value", "qualification", "proposition_ids")),
        "checks": _record({**common, "target_ids": _IDS, "proposition_ids": _IDS,
                           "state_ids": _IDS, "outcome": {"type": "string", "enum": sorted(reasoning_graph.OUTCOMES)},
                           "reasoning": _STRING, "supersedes": _IDS},
                          ("id", "anchors", "target_ids", "outcome", "reasoning")),
    }
    return _object({name: {"type": "array", "items": schema}
                    for name, schema in records.items()})


def response_format(metric_name, extracting, graph_enabled):
    """Return the strict provider schema; existing state validators remain final."""
    properties = {
        "metric_name": {"type": "string", "enum": [metric_name]},
        "score": {"type": ["integer", "null"], "enum": [0, 1, None]},
        "reasoning": _STRING,
        "context_requests": {**_IDS, "description": "Missing artifact/source IDs to retrieve before judging; otherwise []. Use score:null when requesting context."},
    }
    if extracting:
        delta = {name: {"type": "array", "items": _coarse_schema(name, *spec)}
                 for name, spec in _RECORDS.items()}
        delta["operation"] = _record({
            "operation_type": {"type": "string", "enum": ["llm", "tool", "coordination"]},
            "entity_name": _STRING, "actor_scope": {"type": "string", "enum": ["root", "peer", "unknown"]},
            "is_delegation": {"type": "boolean"},
            **{key: _STRING for key in ("agent_id", "content_ref", "input_ref", "work_id", "delegation_id", "delegator_agent_id", "outcome")},
            **{key: _IDS for key in ("evidence_refs", "recipient_agent_ids", "coordination_event_ids")},
        }, ("operation_type", "entity_name", "actor_scope", "is_delegation"))
        delta["metadata"] = _object({
            **{key: _nullable(_STRING) for key in ("source_ref", "root_agent_id", "policy_text_ref", "root_request_ref", "final_answer_ref", "tool_definitions_ref")},
            **{key: _nullable(_INTEGER) for key in ("delivery_span_index", "termination_span_index")},
        })
        if graph_enabled:
            delta["reasoning_graph"] = _graph_schema()
        properties["state_delta"] = _nullable(_object(delta))
    return {"type": "json_schema", "json_schema": {
        "name": "span_transition", "strict": True, "schema": _object(properties)}}


def _decode_record(row, json_fields=()):
    if not isinstance(row, dict):
        raise ValueError("Span records must be objects")
    clear = row.pop("clear_fields", [])
    if not isinstance(clear, list) or any(not isinstance(key, str) for key in clear):
        raise ValueError("clear_fields must be a list of field names")
    if any(key not in row or row[key] is not None for key in clear):
        raise ValueError("clear_fields must identify explicit null fields")
    for key in list(row):
        if row[key] is None and key not in clear:
            del row[key]
        elif key in json_fields and isinstance(row[key], str):
            try:
                row[key] = json.loads(row[key])
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{row.get('id', 'record')}.{key}: expected valid JSON inside this string. "
                    f"For text use {json.dumps({key: json.dumps('example text')})}; "
                    f"for an object use {json.dumps({key: '{}'})}; "
                    f"for unknown use {json.dumps({key: 'null'})}. Keep the declared field type."
                ) from exc
    if "events" in row and row["events"] is not None and (
        not isinstance(row["events"], list) or any(not isinstance(event, dict) for event in row["events"])
    ):
        raise ValueError(
            f"{row.get('id', 'record')}.events must decode to an array of event objects, not strings or scalars. "
            'Return event objects inside the JSON-encoded array, or "[]" when no events need recording.'
        )
    return row


def decode_response(result):
    """Decode only declared arbitrary JSON fields, preserving intentional nulls."""
    if not isinstance(result, dict):
        raise ValueError("Span response must be an object")
    result = deepcopy(result)
    requests = result.get("context_requests", [])
    if not isinstance(requests, list) or any(not isinstance(item, str) or not item.strip() for item in requests):
        raise ValueError("context_requests must contain nonempty IDs")
    if result.get("score") is None and not requests:
        raise ValueError("A null score requires context_requests")
    if requests:
        result.pop("state_delta", None)  # Provisional work is never committed.
        return result
    result.pop("context_requests", None)
    delta = result.get("state_delta")
    if delta is None:
        if "state_delta" in result and not requests:
            raise ValueError("Extraction requires state_delta after context retrieval")
        return result
    if not isinstance(delta, dict):
        raise ValueError("state_delta must be an object")
    for name in _RECORDS:
        delta[name] = [_decode_record(row, ("events",)) for row in delta.get(name, [])]
    for name in ("operation", "metadata"):
        delta[name] = _decode_record(delta.get(name, {}))
    graph = delta.get("reasoning_graph")
    if graph is not None:
        if not isinstance(graph, dict) or set(graph) != set(reasoning_graph.COLLECTIONS):
            raise ValueError("reasoning_graph requires all four declared collections")
        for name in reasoning_graph.COLLECTIONS:
            graph[name] = [_decode_record(row, ("properties", "value") if name == "state_values" else ("properties",))
                           for row in graph.get(name, [])]
    return result
