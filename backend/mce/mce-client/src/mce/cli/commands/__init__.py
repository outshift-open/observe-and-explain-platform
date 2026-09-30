#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MCE CLI Commands

All command groups and commands for the MCE CLI.
"""

from __future__ import annotations

from .metric import metric_group
from .provider import provider_group
from .kg import kg_group
from .compute import compute

__all__ = ["metric_group", "provider_group", "kg_group", "compute"]
