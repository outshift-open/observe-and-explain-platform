#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class GoalAlignment(_BaseLLMJudgeConversationMetric):
    """Checks that delegated subgoals preserve the user's root objective and priorities."""

    metadata = SpecRegistry.require("GoalAlignment").metadata

    PROMPT_TEMPLATE = """
You are evaluating Goal Alignment across a multi-agent or multi-turn conversation.

Conversation:
{conversation}

Evaluate whether the root objective, priorities and success criteria are preserved when the task is decomposed and delegated. Do not score whether agents followed their instructions, whether facts survived handoffs, or whether the final deliverable was complete. Different specialists may pursue different scoped subgoals without being misaligned.

Evaluation Criteria:
1. Does each delegated subgoal contribute to the outcome the user requested?
2. Are hard priorities preserved rather than silently replaced by a different objective?
3. Does decomposition keep the meaning of success unchanged?
4. Does any subgoal optimize an irrelevant target or work against the root request?

Scoring Scale (1-5):
1 - Misaligned: subgoals replace or work against the root objective.
2 - Poor: key priorities are dropped or success is redefined in material ways.
3 - Moderate: mostly aligned but some subgoals drift from the request.
4 - Good: aligned with only minor, inconsequential drift.
5 - Excellent: every subgoal clearly serves the root objective and priorities.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
