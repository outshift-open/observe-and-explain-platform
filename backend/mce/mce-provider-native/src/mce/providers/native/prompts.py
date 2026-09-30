#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
# prompts.py
# Central repository for LLM prompts used by native metrics.

RESPONSE_COMPLETENESS_V2 = """
You are an expert AI evaluator of Conversation Completeness.

Task: Evaluate how complete the assistant's responses are in addressing the user's queries.

Input Conversation:
{conversation}

Methodology:
1. Identify all distinct questions, intents, and implied needs in the user's input.
2. Check if the assistant addressed EACH one.
3. Assess the depth: Was the answer superficial or detailed enough?
4. Check for missed constraints or follow-ups.

Scoring Scale (1-5):
1 - Severe Omission: Missed the main question entirely.
2 - Major Gaps: Answered part of it but missed key constraints or sub-questions.
3 - Partial: Answered the main point but lacked detail or missed minor points.
4 - Good: addressed all main points well, minor improvements possible.
5 - Complete: Comprehensive, accurate, and detailed response to all aspects.

Output Format:
Reasoning: <Think step-by-step>
Score: <1-5>
"""

INTENT_RECOGNITION = """
Evaluate the assistant's understanding of the user's intent.
Query: "{query}"
Response: "{response}"

Did the assistant correctly identify the intent?
1. Yes
0. No

Return ONLY the number.
"""

# Add more prompts here...
