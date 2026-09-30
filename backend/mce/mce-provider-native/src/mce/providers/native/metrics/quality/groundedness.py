#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class Groundedness(_BaseLLMJudgeConversationMetric):
    """Evaluates how well responses are grounded in verifiable data."""

    metadata = SpecRegistry.require("Groundedness").metadata

    PROMPT_TEMPLATE = """
You are evaluating Groundedness in a Multi-Agent System conversation.

Conversation:
{conversation}

Evaluation Criteria:
1. Are all factual claims in the responses traceable to provided data, tool outputs, or the conversation context?
2. Does the system avoid speculation, fabrication, or hallucinations?
3. When the system is uncertain, does it acknowledge the limit of its knowledge?

Scoring Scale (1-5):
1 - Severely ungrounded: major fabrications or hallucinations throughout.
2 - Mostly ungrounded: several claims unverifiable or contradicted by context.
3 - Partially grounded: some responses grounded but notable unsupported claims remain.
4 - Mostly grounded: most claims verifiable, only minor unsupported details.
5 - Fully grounded: all claims traceable to context, tool outputs, or known facts.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
