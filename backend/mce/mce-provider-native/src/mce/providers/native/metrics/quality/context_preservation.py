#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class ContextPreservation(_BaseLLMJudgeConversationMetric):
    """Measures how well responses maintain and carry forward conversation context."""

    metadata = SpecRegistry.require("ContextPreservation").metadata

    PROMPT_TEMPLATE = """
You are evaluating Context Preservation across a multi-turn conversation.

Conversation:
{conversation}

Evaluation Criteria:
1. Does each response correctly reference and build on the context established in prior turns?
2. Does the system avoid treating each turn in isolation, losing previously established facts or goals?
3. When the user implicitly refers to prior context, does the system correctly resolve the reference?

Scoring Scale (1-5):
1 - No context preserved: system ignores all prior turns, responses are context-free.
2 - Poor: frequently loses context, treating most turns as independent queries.
3 - Moderate: some context carried forward but notable gaps or mis-resolutions.
4 - Good: context mostly preserved with only minor oversights.
5 - Excellent: rich, accurate context threading maintained throughout.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
