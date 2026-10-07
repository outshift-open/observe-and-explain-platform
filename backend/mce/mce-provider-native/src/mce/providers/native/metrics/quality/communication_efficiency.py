#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class CommunicationEfficiency(_BaseLLMJudgeConversationMetric):
    """Checks for redundant payloads, repeated calls and communication that causes confusion or repair work."""

    metadata = SpecRegistry.require("CommunicationEfficiency").metadata

    PROMPT_TEMPLATE = """
You are evaluating Communication Efficiency between components in a multi-agent conversation.

Conversation:
{conversation}

Evaluate whether communication and coordination are proportionate to the information and control value they add.

Look for: irrelevant payload not needed by the recipient's scoped task; repeated facts, prompts or context adding no new information; broad context dumps (especially the same full history sent in two or more handoffs) that obscure constraints or cause confusion; exact repeated calls, redundant delegations or non-advancing loops; and repair work caused by avoidable communication defects.

Penalize material avoidable burden that has downstream impact (constraint loss, confusion, contradiction, repair work) or that repeatedly transmits payload or performs an operation with no new information, changed input or control value.

Do not penalize communication that supplies necessary evidence, separates specialist scopes, enables independent verification, resolves uncertainty, or is a justified retry after a failure or changed input. Long payloads and operation count alone are not evidence of inefficiency.

Scoring Scale (1-5):
1 - Highly wasteful: repeated zero-information communication or dumps with clear downstream harm.
2 - Poor: significant redundancy with some downstream impact.
3 - Moderate: noticeable redundancy but little harm.
4 - Good: communication is mostly proportionate with minor redundancy.
5 - Excellent: every exchange adds necessary information or control value.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
