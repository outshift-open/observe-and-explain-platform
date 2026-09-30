#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCEClientConfig — configuration dataclass for the MCEClient."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class MCEClientConfig:
    """Configuration for the MCEClient data access layer.

    This object is meant to be built explicitly by callers. CLI and API
    entrypoints may use :meth:`from_env` to translate environment variables into
    an explicit config at the boundary.

    Engine parameters
    -----------------
    engine_max_workers:
        Number of parallel workers for metric computation.
        Mapped to ``MetricEngine(max_workers=...)``.
    engine_strategy:
        Execution strategy passed to ``MetricEngine``.
        Choices: ``thread``, ``process``, ``hybrid``, ``asyncio``.
    """

    kg_host: str | None = None
    kg_user: str | None = None
    kg_password: str | None = None
    kg_database: str | None = None
    metric_cache_path: str | None = None
    engine_max_workers: int = 8
    engine_strategy: str = "hybrid"

    @classmethod
    def from_env(cls) -> "MCEClientConfig":
        """Build an explicit config from environment variables at the boundary."""
        return cls(
            kg_host=os.getenv("KG_DB_HOST") or os.getenv("NEO4J_URI") or None,
            kg_user=os.getenv("KG_DB_USER") or os.getenv("NEO4J_USERNAME") or None,
            kg_password=os.getenv("KG_DB_PASSWORD")
            or os.getenv("NEO4J_PASSWORD")
            or None,
            kg_database=os.getenv("KG_DB_NAME") or os.getenv("NEO4J_DATABASE") or None,
            metric_cache_path=os.getenv("MCE_METRIC_CACHE") or None,
            engine_max_workers=int(os.getenv("MCE_ENGINE_MAX_WORKERS", "8")),
            engine_strategy=os.getenv("MCE_ENGINE_STRATEGY", "hybrid"),
        )

    @property
    def has_kg_connection_config(self) -> bool:
        return all([self.kg_host, self.kg_user, self.kg_password])

    def validate(self) -> None:
        """Raise ValueError if required fields are missing."""
        missing = [
            name
            for name, value in {
                "kg_host": self.kg_host,
                "kg_user": self.kg_user,
                "kg_password": self.kg_password,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(
                "Explicit Neo4j configuration is required; missing: "
                + ", ".join(missing)
            )
