#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Health-check utilities."""

from __future__ import annotations


def healthz() -> dict:
    """Return the health status of the server."""
    return {"status": "ok"}
