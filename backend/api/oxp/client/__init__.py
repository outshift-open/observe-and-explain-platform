#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXP client public exports.

Exports are loaded lazily so utility modules like ``oxp.client.dal`` can be
imported without importing LocalClient and its optional dependencies.
"""

from typing import Any

__all__ = ["OXPAPIClient", "GoldenClient", "LocalClient"]


def __getattr__(name: str) -> Any:
    if name == "OXPAPIClient":
        from oxp.client.base import OXPAPIClient

        return OXPAPIClient
    if name == "GoldenClient":
        from oxp.client.mock import GoldenClient

        return GoldenClient
    if name == "LocalClient":
        from oxp.client.local import LocalClient

        return LocalClient
    raise AttributeError(f"module 'oxp.client' has no attribute {name!r}")
