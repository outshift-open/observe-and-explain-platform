#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
mce-legacy — backward-compatibility adapters for MCE v2.

This package contains IO-dependent providers and legacy CLI commands that
cannot live in the pure ``mce-core`` package.  Install it alongside
``mce-core`` when you need the ClickHouse / DAL provider or the V1-style
CLI sub-commands.
"""

from __future__ import annotations

from mce.legacy.facade import LegacyMetricManager
from mce.legacy.legacy_api_provider import LegacyApiProvider

__all__ = ["LegacyMetricManager", "LegacyApiProvider"]
