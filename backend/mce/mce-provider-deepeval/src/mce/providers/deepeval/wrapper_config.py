#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

# Shared DeepEval criteria and evaluation parameters for GEval-based metrics.

try:
    from deepeval.test_case import LLMTestCaseParams
except Exception:
    LLMTestCaseParams = None

COHERENCE_CRITERIA = (
    "Coherence evaluates whether the response is logically structured, internally "
    "consistent, and easy to follow. Coherence measures also whether response is "
    "succinct and free from unnecessary elaboration, verbosity, or repetition with "
    "no contradictions or non sequiturs."
)

EVALUATION_STEPS_GROUNDEDNESS: list[str] = [
    "If (and ONLY IF the user provided in their input any information retrieval context "
    "(such as information sources, raw documents, etc) to base the answer on, determine "
    "if the assertions and claims provided in the answer are faithful to the provided "
    "retrieval context.",
    "If there is no retrieval context provided, give an average score.",
]

EVALUATION_STEPS_TONALITY: list[str] = [
    "If the situation requires it (e.g if the user seems to be in a situation where "
    "their emotions are not neutral : happy, sad, angry, etc), check if there is a fair "
    "level of understanding, respect and compassion in the response when applicable.",
    "Determine whether the actual output maintains a professional tone throughout.",
    "Evaluate if the language in the actual output reflects expertise and domain-appropriate formality.",
    "Ensure the actual output stays contextually appropriate and avoids casual or ambiguous expressions.",
    "Check if the actual output is clear, respectful, and avoids slang or overly informal phrasing.",
]

CRITERIA_CORRECTNESS = (
    "Determine if the 'actual output' is correct based on the 'expected output' if "
    "provided. If the 'expected output' is missing or is empty, analyze the 'input' "
    "and the 'actual output' and determine if it is correct to the best of your knowledge."
)

CRITERIA_GENERAL_STRUCTURE = (
    "Evaluate the following aspects of the general structure and style of the 'actual output': "
    "(1) grammatical correctness, (2) readability, (3) clarity and informativeness."
)

if LLMTestCaseParams is None:
    COHERENCE_EVAL_PARAMS = []
    GROUNDEDNESS_EVAL_PARAMS = []
    TONALITY_EVAL_PARAMS = []
    CORRECTNESS_EVAL_PARAMS = []
    GENERAL_STRUCTURE_EVAL_PARAMS = []
else:
    COHERENCE_EVAL_PARAMS = [LLMTestCaseParams.ACTUAL_OUTPUT]
    GROUNDEDNESS_EVAL_PARAMS = [
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ]
    TONALITY_EVAL_PARAMS = [LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT]
    CORRECTNESS_EVAL_PARAMS = [
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.EXPECTED_OUTPUT,
    ]
    GENERAL_STRUCTURE_EVAL_PARAMS = [LLMTestCaseParams.ACTUAL_OUTPUT]
