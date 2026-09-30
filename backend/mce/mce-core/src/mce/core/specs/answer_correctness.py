#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs._registry import MetricSpec
from mce.core.metadata import MetricLayer, MetricNature, MetricScope
from mce.core.metric import MetricRequirements

SPEC = MetricSpec(
    name="AnswerCorrectness",
    description="Evaluates the factual accuracy and correctness of the responses provided.",
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.STOCHASTIC,
    scope=MetricScope.SESSION,
    ontology_class="AnswerCorrectness",
    input_requirements=MetricRequirements(
        text_fields=["conversation_data", "conversation_text", "transcript"],
    ),
)
