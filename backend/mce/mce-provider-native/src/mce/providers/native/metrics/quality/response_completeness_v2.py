#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

# ResponseCompletenessV2 alias — points to the current (v1-compatible) implementation.
from mce.providers.native.metrics.quality.response_completeness_v1 import (  # noqa: F401
    ResponseCompleteness as ResponseCompletenessV2,
)

__all__ = ["ResponseCompletenessV2"]
