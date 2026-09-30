#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeConversationMetric


class ComponentConflictRate(_BaseLLMJudgeConversationMetric):
    """Evaluates component cooperation in a MAS conversation.

    Value semantics (consistent with framework convention — higher = better):
    1.0 = perfect cooperation, no conflicts.
    0.0 = pervasive conflicts, severely disrupted execution.
    """

    metadata = SpecRegistry.require("ComponentConflictRate").metadata

    PROMPT_TEMPLATE = """
You are evaluating Component Cooperation in a Multi-Agent System conversation.

Conversation:
{conversation}

Evaluation Criteria:
1. Do all components (agents, tools, sub-systems) produce consistent, non-conflicting outputs?
2. Are there any logical inconsistencies or data conflicts between what different components report?
3. How frequently do conflicts appear, and how severely do they disrupt the overall execution?

Scoring Scale (1-5) — higher means BETTER cooperation:
1 - Pervasive conflicts: constant contradictions that severely disrupt execution.
2 - Frequent conflicts: recurring contradictions that degrade system coherence.
3 - Moderate conflicts: noticeable contradictions that require resolution.
4 - Rare, trivial conflicts: minor inconsistencies with negligible impact.
5 - No conflicts: all components are consistent and cooperate seamlessly.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
