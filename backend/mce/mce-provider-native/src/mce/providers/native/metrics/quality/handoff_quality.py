#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class HandoffQuality(_BaseLLMJudgeConversationMetric):
    """Checks that handoffs carry the context, constraints and identifiers the recipient needs."""

    metadata = SpecRegistry.require("HandoffQuality").metadata

    PROMPT_TEMPLATE = """
You are evaluating Handoff Quality between components in a multi-agent conversation.

Conversation:
{conversation}

A good handoff names the task, includes material context already known to the sender, preserves important constraints and identifiers, and receives a response that addresses the requested scope or transparently reports an inability.

Penalize only when a material field, identifier, constraint or scope requirement was known to the sender, was needed by the recipient and not obtainable independently, was omitted, corrupted or ambiguously encoded (or the response ignored a clear requested scope), and this caused a downstream error that was not recovered.

Do not penalize: a transparent tool failure or inability; a reasonable clarification request; a missing item that the sender supplied on retry (at most a minor issue); a constraint deliberately withheld from a component not responsible for enforcing it; or upstream fabricated content the interface did not change.

Scoring Scale (1-5):
1 - Handoffs routinely lose critical context, causing unrecovered downstream errors.
2 - Poor: significant omissions or ambiguity with downstream impact.
3 - Moderate: some gaps, mostly recovered before the final outcome.
4 - Good: handoffs are clear with only minor recovered issues.
5 - Excellent: every handoff is complete, scoped and answered appropriately.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
