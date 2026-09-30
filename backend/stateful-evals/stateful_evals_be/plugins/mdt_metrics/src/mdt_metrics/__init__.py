#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

"""Core evaluation primitives for stateful agent trajectory assessment.

Three atomic metrics that are necessary and sufficient for determining
whether an agent trajectory is correct:

- Groundedness: factual claims trace to evidence
- IntentRecognition: all requirements identified, tracked, and addressed
- Relevancy: no contradictions, valid reasoning chains
"""

from .groundedness import Groundedness
from .intent_recognition import IntentRecognition
from .relevancy import Relevancy

__version__ = "0.2.0"

__all__ = [
    "Groundedness",
    "IntentRecognition",
    "Relevancy",
]
