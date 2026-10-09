#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class ConstraintSatisfaction(_BaseLLMJudgeConversationMetric):
    """Checks the final plan item by item against tool facts and hard user/policy constraints."""

    metadata = SpecRegistry.require("ConstraintSatisfaction").metadata

    PROMPT_TEMPLATE = """
You are evaluating Constraint Satisfaction for the final outcome of a conversation.

Conversation:
{conversation}

Read the final plan or answer item by item. For each thing it proposes (an action, visit, booking, purchase, time, amount or total), compare it with the facts tools returned (availability, opening times, capacities, prerequisites and lead times, eligibility, prices) and with the hard constraints in the user request and applicable policy (budgets, dates, durations, required inclusions or exclusions, safety and eligibility rules).

Penalize contradictions: placing an item a tool says is unavailable, keeping an item whose prerequisite cannot be met in the plan's timeframe, combining items that cannot all hold together (overlapping times, unreachable sequences), exceeding a limit, or silently relaxing a constraint. A caveat or suggestion to double-check does not resolve a contradiction the plan still presents as part of the outcome.

Compatible conversions are valid (five travel days can require four hotel nights; decimals and percentages can express the same rate). Do not treat a preference as a hard constraint unless the request makes it one. Judge only contradictions between what is proposed and what is known; incompleteness and unsupported facts belong to other metrics.

Scoring Scale (1-5):
1 - Final outcome violates multiple hard constraints or tool facts.
2 - Poor: at least one major violation.
3 - Moderate: minor violations or contradictions retained in the outcome.
4 - Good: constraints satisfied with only trivial issues.
5 - Excellent: the outcome is consistent with all tool facts and hard constraints.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
