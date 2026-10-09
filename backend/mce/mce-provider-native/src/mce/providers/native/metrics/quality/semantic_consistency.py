#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class SemanticConsistency(_BaseLLMJudgeConversationMetric):
    """Evaluates consistency across responses in a conversation."""

    metadata = SpecRegistry.require("SemanticConsistency").metadata

    PROMPT_TEMPLATE = """
You are evaluating Semantic Consistency across a multi-turn conversation.

Conversation:
{conversation}

Evaluation Criteria:
1. Are all responses internally consistent — no contradictions or conflicting facts?
2. Does the system maintain a consistent tone, terminology, and style throughout?
3. Does the system avoid reversing stated positions without justification?

Scoring Scale (1-5):
1 - Severely inconsistent: major contradictions that undermine the conversation.
2 - Frequently inconsistent: several notable contradictions or style shifts.
3 - Moderately consistent: mostly coherent but noticeable inconsistencies present.
4 - Mostly consistent: minor and inconsequential inconsistencies only.
5 - Fully consistent: no contradictions, coherent tone and content throughout.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
