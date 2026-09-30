#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs._registry import MetricSpec
from mce.core.metadata import MetricLayer, MetricNature, MetricScope
from mce.core.metric import MetricRequirements

SPEC = MetricSpec(
    name="Hallucination",
    description="Detects hallucinations in the model's response.",
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.STOCHASTIC,
    scope=MetricScope.EXECUTION_ELEMENT,
    ontology_class="Hallucination",
    input_requirements=MetricRequirements(
        text_fields=["input_payload", "output_payload", "context"],
    ),
)
