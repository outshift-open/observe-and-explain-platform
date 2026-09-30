#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from mce.core.metric import MetricRequirements
from mce.core.metadata import MetricLayer, MetricNature, MetricScope
from mce.core.specs._registry import MetricSpec

"""CompletionRate metric specification.

Definition
----------
This metric computes completion as:

``1 - (failed sessions / total sessions)``

At single-session scope, the metric returns ``1.0`` for a completed session and
``0.0`` for a failed session.

Inference rule
--------------
The knowledge graph is not required to persist a canonical session-level
pass/fail boolean for this metric. When an explicit ``completion`` flag is not
available in the metric context, the implementation derives session completion
from child execution nodes via ``contains_error`` -- the provider-derived
signal from each call's own ``success`` field (``contains_error = success is
False``; no signal recorded is not a failure):

- a session is considered completed when not all LLM calls failed and not all
    tool calls failed, for each category that is present

Implementation intent
---------------------
This inference belongs to the metric implementation, not to the provider
layer.
"""

SPEC = MetricSpec(
    name="CompletionRate",
    description=(
        "Computes completion as 1 - (failed sessions / total sessions). "
        "For a single session, returns 1.0 when the session completed and 0.0 when it failed."
    ),
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.DETERMINISTIC,
    scope=MetricScope.SESSION,
    ontology_class="CompletionRate",
    input_requirements=MetricRequirements(
        required_entities=["mas:LLMCall", "mas:ToolCall"],
        scalar_fields=["contains_error", "completion"],
        include_edges=True,
    ),
)
