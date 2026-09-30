#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs._registry import MetricSpec
from mce.core.metadata import (
    EdgeFacet,
    MetricLayer,
    MetricNature,
    MetricScope,
    NodeFacet,
    RetrievalRequest,
    RetrievalScope,
)
from mce.core.metric import MetricRequirements

SPEC = MetricSpec(
    name="AgentToAgentInteractions",
    description=(
        "Collects directed transition counts derived from the ordered AgentCall "
        "sequence of a session."
    ),
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.DETERMINISTIC,
    scope=MetricScope.SESSION,
    ontology_class="AgentToAgentInteractions",
    input_requirements=MetricRequirements(
        required_entities=["mas:AgentCall"],
        include_edges=True,
        allowed_relations=["hasMASCall", "hasAgentCall"],
        retrieval=RetrievalRequest(
            scope=RetrievalScope(),
            nodes=[
                NodeFacet(
                    entity_type="mas:AgentCall",
                    alias="agent_calls",
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
            ],
        ),
    ),
)
