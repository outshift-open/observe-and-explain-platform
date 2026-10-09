#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class VerificationQuality(_BaseLLMJudgeConversationMetric):
    """Checks evidence sufficiency, contradiction handling and feasibility checks before synthesis."""

    metadata = SpecRegistry.require("VerificationQuality").metadata

    PROMPT_TEMPLATE = """
You are evaluating Verification Quality in a multi-agent or multi-turn conversation.

Conversation:
{conversation}

First decide applicability: look for (a) any stated duty to verify, check, validate, cross-check, review or assess feasibility; (b) any verifier, critique or review step; (c) a final answer or action that combines outputs from two or more components. If none exists, there is nothing to verify and the score is 5.

Otherwise evaluate whether material outputs were checked for evidence sufficiency, same-scope contradiction, prerequisite completion, temporal or logical compatibility and preserved uncertainty before synthesis or action. A schedule built from individually valid facts must still be jointly feasible. An approval that did not examine the evidence (for example a format-only review) does not verify anything. Do not invent conflicts between different scopes that the final answer distinguishes. Handoff clarification, transparent failure, incompleteness and factual invention belong to other metrics.

Scoring Scale (1-5):
1 - Unsupported or incompatible outputs are treated as verified and used downstream, or required checks were skipped.
2 - Poor: verification is superficial or missing for material outputs.
3 - Moderate: some checks done but material gaps remain.
4 - Good: material outputs are checked with only minor gaps.
5 - Excellent: outputs are thoroughly checked and reconciled, uncertainty preserved (or no verification was applicable).

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
