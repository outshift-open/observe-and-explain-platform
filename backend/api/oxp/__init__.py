#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXP public library interface.

Exports are loaded lazily so submodule imports do not eagerly pull optional
runtime dependencies.
"""

from typing import Any

__all__ = ["OXPAPIClient", "Filters", "LocalClient"]


def __getattr__(name: str) -> Any:
    if name == "OXPAPIClient":
        from oxp.client.base import OXPAPIClient

        return OXPAPIClient
    if name == "LocalClient":
        from oxp.client.local import LocalClient

        return LocalClient
    if name == "Filters":
        from oxp.models.otel_traces import Filters

        return Filters
    raise AttributeError(f"module 'oxp' has no attribute {name!r}")
