#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class InstructionFollowing(_BaseLLMJudgeConversationMetric):
    """Checks whether agents followed their assigned scope, procedure and constraints."""

    metadata = SpecRegistry.require("InstructionFollowing").metadata

    PROMPT_TEMPLATE = """
You are evaluating Instruction Following across a multi-agent or multi-turn conversation.

Conversation:
{conversation}

Judge each component only from the instructions and constraints available to it in its handoff or contract. Keep this separate from context preservation: a constraint can be transmitted perfectly but disobeyed. A required delegation or tool call is satisfied when the correct call was attempted, even if it returned an error; a downstream failure is not an instruction violation unless a required retry, escalation or fallback was then ignored. A transparent partial response that does not claim completion follows the instruction. Do not penalize unsupported facts or incomplete outcomes here unless they contradict a binding instruction.

Evaluation Criteria:
1. Does each agent stay within its assigned scope and follow its required procedure?
2. Are supplied constraints respected, and explicit checks (timing, feasibility, etc.) actually carried out?
3. When an instruction cannot be completed, is that reported honestly?
4. Is any instruction ignored, contradicted, bypassed or falsely claimed complete?

Scoring Scale (1-5):
1 - Instructions are routinely ignored, contradicted or falsely claimed complete.
2 - Poor: several material instructions are violated.
3 - Moderate: most instructions are followed but at least one material one is missed.
4 - Good: instructions followed with only minor lapses.
5 - Excellent: all available instructions and constraints are followed, or inability is reported transparently.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
