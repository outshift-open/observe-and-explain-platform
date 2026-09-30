#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Repository factory — returns the right :class:`OtelRepository` for the
current backend (``OXP_LOCAL`` env var)."""

from __future__ import annotations

import os

from oxp.repositories.otel_repository import OtelRepository


def get_otel_repository() -> OtelRepository:
    """Return an :class:`OtelRepository` backed by the active database.

    When the ``OXP_LOCAL`` env var is truthy (default), a SQLite-backed
    repository is returned; otherwise a ClickHouse-backed one.
    """
    if os.getenv("OXP_LOCAL", "true").lower() in ("true", "1", "yes"):
        from oxp.repositories.sqlite_repository import SqliteOtelRepository

        return SqliteOtelRepository()
    else:
        from oxp.repositories.clickhouse_otel_repository import (
            ClickHouseOtelRepository,
        )

        return ClickHouseOtelRepository()
