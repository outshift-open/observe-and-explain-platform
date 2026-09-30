#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
# MCE CLI Package

import warnings

# Suppress Pydantic v1 compatibility warning from opik in Python 3.14+
# Applied at CLI package level to catch warnings before command modules load
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater",
    category=UserWarning,
)
