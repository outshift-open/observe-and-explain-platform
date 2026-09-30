#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class InformationRetention(_BaseLLMJudgeConversationMetric):
    """Measures how well information is retained across multiple interactions."""

    metadata = SpecRegistry.require("InformationRetention").metadata

    PROMPT_TEMPLATE = """
You are evaluating Information Retention across a multi-turn conversation.

Conversation:
{conversation}

Evaluation Criteria:
1. Does the system correctly remember and reference facts or preferences stated earlier in the conversation?
2. Does it avoid contradicting itself or forgetting key details?
3. Is retained information applied accurately in later turns?

Scoring Scale (1-5):
1 - No retention: key information forgotten entirely, contradictions throughout.
2 - Poor retention: frequently forgets important details established earlier.
3 - Moderate: most information retained but lapses or minor contradictions present.
4 - Good: information mostly retained with only trivial inconsistencies.
5 - Excellent: perfect retention and accurate application of all prior context.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
