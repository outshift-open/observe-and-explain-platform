#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs._registry import MetricSpec
from mce.core.metadata import MetricLayer, MetricNature, MetricScope

SPEC = MetricSpec(
    name="ToolError",
    description="Checks if a specific tool execution resulted in an error.",
    layer=MetricLayer.EXECUTION,
    nature=MetricNature.DETERMINISTIC,
    scope=MetricScope.EXECUTION_ELEMENT,
    ontology_class="ToolError",
)
