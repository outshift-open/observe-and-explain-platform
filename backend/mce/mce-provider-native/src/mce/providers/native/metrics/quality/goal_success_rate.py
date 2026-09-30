#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeQAMetric


class GoalSuccessRate(_BaseLLMJudgeQAMetric):
    """Measures the rate at which the assistant achieves the input goal."""

    metadata = SpecRegistry.require("GoalSuccessRate").metadata

    PROMPT_TEMPLATE = """
You are evaluating Goal Success Rate for an AI assistant.

User Query / Goal:
{query}

Assistant Response:
{response}

Evaluation Criteria:
1. Does the response directly address the goal specified by the user?
2. Are all explicit requirements and constraints from the goal fulfilled?
3. Is the response fully actionable and sufficient, or does it leave the goal partially unmet?

Scoring Scale (1-5):
1 - Complete failure: the goal is entirely ignored or fundamentally misunderstood.
2 - Significant failure: core requirements missed; user goal substantially unmet.
3 - Partial: main goal addressed but key constraints or sub-goals left unfulfilled.
4 - Good: goal met with only minor gaps or missing nuances.
5 - Full success: goal completely and correctly achieved in every respect.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
