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

"""WorkflowEfficiency metric specification.

Definition
----------
This metric measures how repetitive the agent routing pattern is within a
session. Starting from the ordered sequence of ``mas:AgentCall`` instances for
the session, the implementation derives the directed transition sequence between
consecutive agent calls.

For an agent-call sequence ``A, B, A, Z, A, B, A``, the derived transitions are:

``A->B, B->A, A->Z, Z->A, A->B, B->A``

- total transitions = 6
- unique directed transitions = 4
- workflow efficiency = 4 / 6 = 0.6667

Interpretation
--------------
A score close to 1 means the workflow uses many distinct agent-to-agent
handoffs relative to its total number of handoffs. A lower score means the
workflow repeats the same routing patterns more often.

Implementation intent
---------------------
This metric should not require precomputed ``agent_transitions`` from the data
provider. The provider should retrieve the ordered ``mas:AgentCall`` sequence
for the session using ontology-respecting traversal:

``Session -[:hasMASCall]-> MASCall -[:hasAgentCall]-> AgentCall``

The concrete metric implementation then derives the transition sequence locally
from that ordered ``AgentCall`` sequence.
"""

SPEC = MetricSpec(
    name="WorkflowEfficiency",
    description=(
        "Measures how diverse the directed agent-to-agent routing pattern is "
        "within a session, computed as unique consecutive AgentCall transitions "
        "divided by total consecutive AgentCall transitions. "
        "Example: X, Y, X, Z, X, Y, X -> 4 unique transitions / 6 total = 66.67%."
    ),
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.DETERMINISTIC,
    scope=MetricScope.SESSION,
    ontology_class="WorkflowEfficiency",
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
