#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mce.core.metric import MetricRequirements
from mce.core.metadata import (
    EdgeFacet,
    MetricLayer,
    MetricNature,
    MetricScope,
    NodeFacet,
    RetrievalRequest,
    RetrievalScope,
)
from mce.core.specs._registry import MetricSpec

"""LLMErrorRate metric specification.

Definition
----------
This metric computes the fraction of LLM calls that failed within the requested
scope:

``number_of_failed_llm_calls / total_number_of_llm_calls``

Inference rule
--------------
Failure is read from ``contains_error``, which the provider layer derives from
each ``mas:LLMCall``'s ``success`` field (``contains_error = success is
False``; no signal recorded -- ``success`` absent -- is not a failure). There
is no raw ``status``/``error`` field on any KG node to read instead; ``success``
is the only execution-outcome signal the ontology carries.
"""

SPEC = MetricSpec(
    name="LLMErrorRate",
    description="Calculates the percentage of LLM calls that resulted in an error.",
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.DETERMINISTIC,
    scope=MetricScope.SESSION,
    ontology_class="LLMErrorRate",
    input_requirements=MetricRequirements(
        required_entities=["mas:LLMCall"],
        scalar_fields=["contains_error"],
        include_edges=True,
        allowed_relations=["hasMASCall", "hasAgentCall", "hasLLMCall"],
        retrieval=RetrievalRequest(
            scope=RetrievalScope(),
            nodes=[
                NodeFacet(
                    entity_type="mas:LLMCall",
                    alias="llm_spans",
                    fields=["id", "contains_error", "startTime"],
                    order_by=["startTime"],
                )
            ],
            edges=[
                EdgeFacet(
                    relation_type="hasMASCall",
                    source_entity="mas:Session",
                    target_entity="mas:MASCall",
                ),
                EdgeFacet(
                    relation_type="hasAgentCall",
                    source_entity="mas:MASCall",
                    target_entity="mas:AgentCall",
                ),
                EdgeFacet(
                    relation_type="hasLLMCall",
                    source_entity="mas:AgentCall",
                    target_entity="mas:LLMCall",
                ),
            ],
        ),
    ),
)
