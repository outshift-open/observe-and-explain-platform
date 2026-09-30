#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from pkgutil import extend_path

import warnings

# Allow multiple workspace packages to contribute to top-level `mce`.
__path__ = extend_path(__path__, __name__)

# Suppress Pydantic v1 compatibility warning from opik in Python 3.14+
# Must be at the top level before any other imports
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater",
    category=UserWarning,
)

# Expose key public components
try:
    from .core.types import MetricResult as MetricResult
    from .core.metric import Metric as Metric
    from .engine.engine import MetricEngine as MetricEngine

    __all__ = ["MetricResult", "Metric", "MetricEngine"]
except ImportError:
    __all__: list[str] = []
