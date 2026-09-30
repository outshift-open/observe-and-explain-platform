#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""FastAPI router for the /features endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from oxp.api.api_v1.endpoints.helpers import get_client

router = APIRouter()


@router.get("/info")
def features_info(request: Request) -> Any:
    """Return descriptive information about this endpoint."""
    return get_client().info(domain="features")
