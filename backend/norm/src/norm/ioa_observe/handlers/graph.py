#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Handler for the "*.graph" span name: declared MAS/Agent structural nodes.

This is the one authoritative source of "declared" structural data, so it
always overwrites (``registry.upsert``) rather than fills-in-if-absent --
every other handler only ever creates the same MAS/Agent ids as undeclared
placeholders (``registry.add``, keep-first), so whichever one of those ran
first never blocks this handler's richer data from landing.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from oxp_ontology.models.base import KGBase
from oxp_ontology.models.edges import belongsToMAS
from oxp_ontology.models.nodes import MAS, Agent, StructuralElement

from ..fields import get_application_id
from ..registry import Registry

log = logging.getLogger(__name__)


def _declare(
    registry: Registry,
    cls: type[KGBase],
    node_id: str,
    *,
    name: str = "",
    description: str = "",
) -> KGBase:
    """Set the declared (graph-sourced) version of a structural node.

    Keeps an existing declared record as-is (e.g. two "*.graph" spans for the
    same app) rather than reconstructing it, but overwrites any undeclared
    placeholder another handler already created for this id.
    """
    existing: StructuralElement = registry.get(cls, node_id)
    if existing is not None and existing.declared:  # type: ignore[attr-defined]
        return existing
    return registry.upsert(
        cls.model_validate(
            {
                "id": node_id,
                "name": name or node_id,
                "description": description,
                "declared": True,
            }
        )
    )


def handle_graph(
    span: dict[str, Any],
    span_attrs: dict[str, Any],
    registry: Registry,
) -> None:
    application_id = get_application_id(span, span_attrs)
    if not application_id:
        return
    name = str(span_attrs.get("ioa_observe.entity.name") or application_id)
    description = str(span_attrs.get("ioa_observe.entity.description") or "")
    _declare(registry, MAS, application_id, name=name, description=description)

    graph_raw = span_attrs.get("gen_ai.ioa.graph")
    if not graph_raw:
        return
    try:
        graph_data: dict = json.loads(graph_raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        log.warning(
            "Could not parse gen_ai.ioa.graph for span %s -- skipping structural "
            "graph extraction (span name %s)",
            span.get("SpanId"),
            span.get("SpanName"),
        )
        return

    graph_nodes: dict[str, dict] = graph_data.get("nodes") or {}
    for node_id, node in graph_nodes.items():
        if node_id in ("__start__", "__end__"):
            continue
        agent_name = str(node.get("name") or node_id)
        agent: Agent = _declare(registry, Agent, node_id, name=agent_name)
        registry.add_edge(belongsToMAS(source_id=agent.id, target_id=application_id))
