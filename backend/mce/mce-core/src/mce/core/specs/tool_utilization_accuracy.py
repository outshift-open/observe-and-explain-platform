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

"""ToolUtilizationAccuracy metric specification.

Definition
----------
This metric evaluates whether a tool call was appropriate for the agent input,
whether the arguments were well formed, and whether the returned output helped
address the request.

Canonical input shape
---------------------
The base metric is written against the ontology shape and expects ToolCall data
to be provided with the following canonical field names:

- ``toolArguments``
- ``outputContent``
- ``toolName``
- optional ``tool_definition``

Compatibility note
------------------
Historical payloads may still expose legacy field names such as
``inputParams`` or ``toolOutput``. Support for those legacy names must stay in
the dedicated workaround module, not in the provider layer and not as the base
contract of the metric.
"""

SPEC = MetricSpec(
    name="ToolUtilizationAccuracy",
    description="Determines if the tool usage was accurate with respect to the input.",
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.STOCHASTIC,
    scope=MetricScope.EXECUTION_ELEMENT,
    ontology_class="ToolUtilizationAccuracy",
    input_requirements=MetricRequirements(
        required_entities=["mas:ToolCall"],
        text_fields=[
            "toolArguments",
            "outputContent",
            "tool_definition",
            "toolName",
        ],
        include_edges=True,
        allowed_relations=["hasMASCall", "hasAgentCall", "hasToolCall"],
        retrieval=RetrievalRequest(
            scope=RetrievalScope(),
            nodes=[
                NodeFacet(
                    entity_type="mas:ToolCall",
                    alias="tool_spans",
                    fields=[
                        "id",
                        "toolArguments",
                        "outputContent",
                        "tool_definition",
                        "toolName",
                        "startTime",
                    ],
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
                    relation_type="hasToolCall",
                    source_entity="mas:AgentCall",
                    target_entity="mas:ToolCall",
                ),
            ],
        ),
    ),
)
