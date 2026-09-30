#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs._registry import MetricSpec
from mce.core.metadata import MetricLayer, MetricNature, MetricScope
from mce.core.metric import MetricRequirements

SPEC = MetricSpec(
    name="Toxicity",
    description="Detects and evaluates the presence of toxic language, hate speech, or harmful content.",
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.DETERMINISTIC,
    scope=MetricScope.SESSION,
    ontology_class="Toxicity",
    input_requirements=MetricRequirements(
        text_fields=["conversation_data", "conversation_text", "transcript"],
    ),
)
