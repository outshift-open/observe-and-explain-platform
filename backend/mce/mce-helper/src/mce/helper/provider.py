#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mce-helper.provider — re-exports from mce.helper.interfaces.

Backward-compatible shim: code that does ``from mce.helper import MCEProvider``
continues to work.

Ownership:
  mce-helper owns MetricsProvider (metric CRUD contracts).
  DataProvider (KG-specific: resolve_session_id + fetch) lives in oxp-api.
"""

from __future__ import annotations

from mce.helper.interfaces import MetricsProvider  # noqa: F401

# Backward-compat alias kept for any code using MCEProvider
MCEProvider = MetricsProvider

__all__ = ["MetricsProvider", "MCEProvider"]
