#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

"""Thin wrapper around MCEWorkerService for the standalone mce-worker."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from mce.client.config import MCEClientConfig
from mce.client.worker import MCEWorkerService

logger = logging.getLogger(__name__)


class MCEWrapper:
    """Standalone wrapper for :class:`MCEWorkerService`.

    Parameters
    ----------
    config_path:
        Path to ``mce_config.yaml``.
    neo4j_uri:
        Neo4j Bolt URI.
    neo4j_user:
        Neo4j username.
    neo4j_password:
        Neo4j password.
    neo4j_database:
        Neo4j database name.
    llm_api_key:
        API key for LLM-as-a-judge metrics.
    llm_model_name:
        LLM model identifier (e.g. ``gpt-4o-mini``).
    llm_base_model_url:
        Optional custom base URL for the LLM API.
    metrics:
        Optional list of metric names to compute.
    debug:
        Enable verbose debug logging.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        neo4j_uri: str | None = None,
        neo4j_user: str | None = None,
        neo4j_password: str | None = None,
        neo4j_database: str | None = None,
        llm_api_key: str | None = None,
        llm_model_name: str | None = None,
        llm_base_model_url: str | None = None,
        metrics: list[str] | None = None,
        debug: bool = False,
    ) -> None:
        if any([llm_api_key, llm_model_name, llm_base_model_url]):
            from mce.engine.llm import LLMService

            LLMService.configure(
                mode="live",
                api_key=llm_api_key,
                model=llm_model_name,
                base_url=llm_base_model_url,
            )

        client_config = self._build_client_config(
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
            neo4j_database=neo4j_database,
        )

        self._service = MCEWorkerService(
            config_path=config_path,
            client_config=client_config,
        )
        self._metrics = metrics or []
        self._debug = debug
        logger.info("MCEWrapper ready — delegate: %r", self._service._cfg)

    @staticmethod
    def _build_client_config(
        neo4j_uri: str | None,
        neo4j_user: str | None,
        neo4j_password: str | None,
        neo4j_database: str | None,
    ) -> MCEClientConfig | None:
        if neo4j_uri is None and neo4j_user is None and neo4j_password is None:
            return None

        missing = [
            name
            for name, value in {
                "neo4j_uri": neo4j_uri,
                "neo4j_user": neo4j_user,
                "neo4j_password": neo4j_password,
            }.items()
            if value is None
        ]
        if missing:
            raise ValueError(f"MCEWrapper requires explicit Neo4j connection attributes; missing: {', '.join(missing)}")

        return MCEClientConfig(
            kg_host=neo4j_uri,
            kg_user=neo4j_user,
            kg_password=neo4j_password,
            kg_database=neo4j_database,
        )

    def process_session(self, session_id: str) -> list[dict[str, Any]]:
        """Compute metrics for a single session."""
        return self._service.process_session(session_id)

    async def process_mce_session(
        self, session_id: str, local_file: str | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """Async API compatible with BaseWorker.handle_message flow."""
        del local_file
        return {"session_metrics": self.process_session(session_id)}
