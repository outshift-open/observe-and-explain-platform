#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics._base import _BaseLLMJudgeQAMetric


class IntentRecognitionAccuracy(_BaseLLMJudgeQAMetric):
    """Measures how well the assistant recognizes and responds to user intents."""

    metadata = SpecRegistry.require("IntentRecognitionAccuracy").metadata

    PROMPT_TEMPLATE = """
You are evaluating Intent Recognition Accuracy for an AI assistant.

User Query:
{query}

Assistant Response:
{response}

Evaluation Criteria:
1. Does the system correctly identify the user's primary intent?
2. Does the response address the identified intent accurately and completely?
3. If the query is ambiguous, does the system resolve or clarify the ambiguity appropriately?

Scoring Scale (1-5):
1 - Complete miss: the system fails to identify the intent and responds off-topic.
2 - Significant miss: intent partially identified but the response substantially misses the mark.
3 - Moderate: correct intent identified but response has notable gaps in addressing it.
4 - Good: intent correctly identified and well-addressed with only minor imprecisions.
5 - Excellent: intent precisely identified and fully, appropriately addressed.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """
