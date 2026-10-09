#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class ConfidenceCalibration(_BaseLLMJudgeConversationMetric):
    """Checks that uncertainty is preserved and confidence is justified by evidence."""

    metadata = SpecRegistry.require("ConfidenceCalibration").metadata

    PROMPT_TEMPLATE = """
You are evaluating Confidence Calibration across a multi-agent or multi-turn conversation.

Conversation:
{conversation}

Evaluate whether claims keep an appropriate level of certainty as evidence moves between components and into the final answer. Ordinary disagreement is not miscalibration, and a concise final answer need not repeat every hedge when the cited evidence is conclusive. Do not duplicate a pure factual fabrication finding unless the defect is specifically an unjustified change in confidence.

Evaluation Criteria:
1. Are estimates, hypotheses, unavailable data, disagreement and verified facts kept distinct?
2. Does confidence rise only when later evidence justifies it?
3. Is uncertainty stripped, or an unsupported hypothesis upgraded to fact?
4. Is material dissent suppressed, or a claim endorsed more strongly than its evidence supports?

Scoring Scale (1-5):
1 - Badly miscalibrated: uncertainty stripped and unsupported claims stated as fact.
2 - Poor: several material claims are overstated or dissent is suppressed.
3 - Moderate: mostly calibrated with notable overstatement or lost hedges.
4 - Good: confidence tracks evidence with only minor lapses.
5 - Excellent: confidence consistently matches the strength of the evidence.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
