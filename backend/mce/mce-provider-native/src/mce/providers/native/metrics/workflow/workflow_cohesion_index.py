#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class WorkflowCohesionIndex(_BaseLLMJudgeConversationMetric):
    """Measures how well components work together as a cohesive workflow."""

    metadata = SpecRegistry.require("WorkflowCohesionIndex").metadata

    PROMPT_TEMPLATE = """
You are evaluating Workflow Cohesion in a Multi-Agent System.

Conversation / Execution Trace:
{conversation}

Evaluation Criteria:
1. Do the components interact smoothly with clear handoff and minimal friction?
2. Is there a logical, purposeful flow between the different stages of the workflow?
3. Does the system maintain consistency and avoid unnecessary redundancy across stages?

Scoring Scale (1-5):
1 - No cohesion: components operate independently with no clear integration.
2 - Poor cohesion: sporadic coordination, frequent gaps or duplications between stages.
3 - Moderate: workflow is generally logical but has notable inefficiencies or gaps.
4 - Good: well-integrated workflow with only minor coordination issues.
5 - Excellent: seamless, highly cohesive workflow with purposeful stage-to-stage transitions.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
