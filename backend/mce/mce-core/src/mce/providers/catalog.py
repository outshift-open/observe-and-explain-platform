#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Compatibility shim — all catalog logic has moved to mce.core.registry.discovery.

Import from ``mce.core.registry.discovery`` directly going forward.
This module exists only to keep old imports working during the transition.
"""

from __future__ import annotations

import warnings
from mce.core.registry.discovery import (
    discover_all_metrics as get_default_metrics,
    get_provider_name,
    serialize_metric_catalog_format,
)

warnings.warn(
    "mce.providers.catalog is deprecated; import from mce.core.registry.discovery instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "get_default_metrics",
    "get_provider_name",
    "serialize_metric_catalog_format",
]
