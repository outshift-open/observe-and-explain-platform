#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""How metrics are stored in the knowledge graph: the ontology's Metric + MetricResult.

::

    (r:MetricResult {id, name, result, reasoning, timestamp, evaluation*})
        -[:ofMetricType]-> (d:Metric {id, name, metricProvider, unit, valueRange})
    (r:MetricResult) -[:measures]-> (t)

``Metric`` is the *definition*: one node per metric name and provider (so
``Groundedness`` computed by ``Native`` and by ``DeepEval`` are two definitions).
``MetricResult`` is one *observation* of it. ``t`` is what was measured: a
``Session`` (found by ``sessionId``) or an execution element, an
``LLMCall``/``ToolCall``/``AgentCall``... (found by ``spanId``). There is no
``hasMetric`` edge and no ``Span`` node.

A result is keyed by its definition and the measured resource, so computing a
metric again overwrites the previous observation instead of adding one.

The node properties are exactly the fields of the models generated from the
ontology (``oxp_ontology.models.nodes.Metric`` / ``MetricResult``); every write
is validated against them.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from oxp_ontology.models.nodes import Metric as MetricModel
from oxp_ontology.models.nodes import MetricResult as MetricResultModel

# MetricResult.metadata key (set by the MCE and the stateful-eval worker) ->
# field of MetricResult for the LLM cost of computing a metric.
_EVALUATION_FIELDS: dict[str, str] = {
    "evaluation_model": "evaluationModel",
    "evaluation_prompt_tokens": "evaluationPromptTokenCount",
    "evaluation_completion_tokens": "evaluationCompletionTokenCount",
    "evaluation_total_tokens": "evaluationTotalTokenCount",
    "evaluation_cost_usd": "evaluationCost",
}
EVALUATION_KEYS = tuple(_EVALUATION_FIELDS)

# API metric catalog unit -> (ontology unit, value range)
_UNITS: dict[str, tuple[str, str]] = {
    "PERCENTAGE": ("dimensionless", "0.0-1.0"),
    "DOLLAR": ("USD", "non-negative"),
    "MILLISECONDS": ("ms", "non-negative"),
    "TOKENS": ("tokens", "non-negative integer"),
    "SCALAR": ("dimensionless", ""),
}

Target = Literal["session", "execution", "call", "any", "protocol_execution_report"]


def _digest(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:12]


def metric_definition_id(metric_name: str, provider: str) -> str:
    """Id of the ``Metric`` definition of ``metric_name`` computed by ``provider``."""
    return f"metric:{_digest(provider, metric_name)}"


def _catalog_unit(metric_name: str) -> tuple[str, str]:
    """Ontology unit and value range of a metric, from the API metric catalog."""
    from oxp.core.config import settings

    for category in (getattr(settings, "METRIC_CATEGORIES", None) or {}).values():
        for key, definition in category.items():
            if metric_name in (key, key.rsplit(".", 1)[-1]) and isinstance(
                definition, dict
            ):
                return _UNITS.get(str(definition.get("unit") or ""), ("", ""))
    return "", ""


def metric_definition_properties(metric_name: str, provider: str) -> dict[str, Any]:
    """Properties of the ontology ``Metric`` definition (validated against the model)."""
    unit, value_range = _catalog_unit(metric_name)
    return MetricModel(
        id=metric_definition_id(metric_name, provider),
        name=metric_name,
        metricProvider=provider,
        unit=unit,
        valueRange=value_range,
    ).model_dump()


def metric_result_properties(
    metric_name: str,
    provider: str,
    resource_id: str,
    value: Any,
    reasoning: str = "",
    metadata: dict[str, Any] | None = None,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Properties of the ontology ``MetricResult`` for one observation.

    Validated against the model generated from the ontology, so every stored
    result has the same fields: ``id``, ``name``, ``result``, ``reasoning``,
    ``timestamp`` and the ``evaluation*`` cost fields. A metric that made no LLM
    call carries the model defaults (empty model, zero tokens, zero cost).
    Raises ``pydantic.ValidationError`` if the observation does not fit the
    model, for example a non-numeric ``value`` or cost.
    """
    metadata = metadata or {}
    evaluation = {
        field: metadata[key]
        for key, field in _EVALUATION_FIELDS.items()
        if metadata.get(key) is not None
    }
    return MetricResultModel(
        id=f"metricresult:{_digest(metric_definition_id(metric_name, provider), resource_id)}",
        name=metric_name,
        result=value,
        reasoning=reasoning or "",
        timestamp=timestamp or datetime.now(timezone.utc),
        **evaluation,
    ).model_dump()


# Execution elements (ExecutionElement subclasses, but the Session) carry the span id.
_EXECUTION_LABELS = "LLMCall|ToolCall|AgentCall|CapabilityCall|MASCall|ProcessingCall"

_TARGET_MATCH: dict[str, str] = {
    "session": "MATCH (t:Session {sessionId: $resource_id})",
    "execution": (
        f"MATCH (t:{_EXECUTION_LABELS} {{spanId: $resource_id}})\n"
        "    WHERE $session_id IS NULL OR t.sessionId = $session_id"
    ),
    # A call node by its own id (the trajectory's call id, not the OTel span id).
    "call": (
        f"MATCH (t:{_EXECUTION_LABELS} {{id: $resource_id}})\n"
        "    WHERE $session_id IS NULL OR t.sessionId = $session_id"
    ),
    # A Cognition protocol execution report by its own id: the protocol's evaluation metrics measure it.
    "protocol_execution_report": "MATCH (t:CognitionProtocolExecutionReport {id: $resource_id})",
    "any": (
        "OPTIONAL MATCH (s:Session {sessionId: $resource_id})\n"
        f"    OPTIONAL MATCH (e:{_EXECUTION_LABELS} {{spanId: $resource_id}})\n"
        "    WITH coalesce(s, e) AS t\n"
        "    WHERE t IS NOT NULL"
    ),
}


def write_metric_result_query(
    target: Target,
    resource_id: str,
    definition: dict[str, Any],
    result: dict[str, Any],
    session_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """MERGE a ``MetricResult`` and its ``Metric`` definition onto what it measures.

    ``target`` says what ``resource_id`` is: a ``session`` id, an ``execution``
    element's span id or a ``call`` node's id (both optionally within
    ``session_id``), ``any`` session or span id, or a ``protocol_execution_report``
    by its id.
    Nothing is written if the measured node does not exist.
    """
    query = f"""
    {_TARGET_MATCH[target]}
    MERGE (d:Metric {{id: $definition.id}})
    SET d += $definition
    MERGE (r:MetricResult {{id: $result.id}})
    SET r += $result
    MERGE (r)-[:ofMetricType]->(d)
    MERGE (r)-[:measures]->(t)
    RETURN r.id AS id
    """
    return query, {
        "resource_id": resource_id,
        "session_id": session_id,
        "definition": definition,
        "result": result,
    }


def clean_metrics_query(session_id: str | None) -> tuple[str, dict[str, Any]]:
    """Delete the metric results of a session (or of everything); definitions stay."""
    if session_id:
        return (
            """
            MATCH (r:MetricResult)-[:measures]->(t)
            WHERE t.sessionId = $session_id
            DETACH DELETE r
            RETURN count(r) AS deleted
            """,
            {"session_id": session_id},
        )
    return "MATCH (r:MetricResult) DETACH DELETE r RETURN count(r) AS deleted", {}
