#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class ResponseCompleteness(_BaseLLMJudgeConversationMetric):
    """Evaluates how completely the assistant addressed all user queries."""

    metadata = SpecRegistry.require("ResponseCompleteness").metadata

    PROMPT_TEMPLATE = """
You are evaluating Response Completeness in a conversation.

Conversation:
{conversation}

Methodology:
1. Identify all distinct questions, intents, and implied needs in the user inputs.
2. Check if the assistant addressed EACH one fully.
3. Assess depth: was the answer superficial or detailed enough for the query complexity?
4. Check for missed constraints, follow-up needs, or implicit requirements.

Scoring Scale (1-5):
1 - Severe omission: missed the main question entirely or provided a non-answer.
2 - Major gaps: answered part but missed key constraints or sub-questions.
3 - Partial: addressed the main point but lacked detail or missed minor sub-goals.
4 - Good: addressed all main points well; minor improvements possible.
5 - Complete: comprehensive, accurate, and detailed response to all aspects.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """


# Alias: code that imported ResponseCompletenessV1 continues to work.
ResponseCompletenessV1 = ResponseCompleteness

__all__ = ["ResponseCompleteness", "ResponseCompletenessV1"]
