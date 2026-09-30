#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MCE client setup utilities."""

import logging
from typing import Any, Optional

from mce.core.provider import DataProvider
from .config import MCEClientConfig
from .adapters.json_provider import JsonDataProvider

logger = logging.getLogger(__name__)


def build_oxp_kg_provider(
    client_config: MCEClientConfig | None = None,
    *,
    combined: bool = False,
):
    """Build a oxp-api KG provider from explicit MCE client config."""
    cfg = client_config or MCEClientConfig.from_env()

    try:
        from oxp.providers import OXPKGProvider, Neo4jGraphProvider  # type: ignore[import]
    except ImportError:
        logger.error("OXP API not found. Use oxp-api, --file, or --legacy.")
        return None

    provider_cls = Neo4jGraphProvider if combined else OXPKGProvider
    return provider_cls(
        host=cfg.kg_host,
        username=cfg.kg_user,
        password=cfg.kg_password,
        database=cfg.kg_database,
    )


def setup_data_provider(
    file: str | None = None,
    legacy: bool = False,
    log_info: bool = False,
    kg_provider: Any = None,
    client_config: MCEClientConfig | None = None,
) -> Optional[DataProvider]:
    """
    Initialize appropriate data provider (JSON/Legacy/OXP).

    This function lives in mce-client because it orchestrates dependencies
    (legacy, file io, oxp-api) that mce-core must not know about.

    Args:
        file: Path to JSON file (if using file-based provider)
        legacy: Use legacy ClickHouse API provider
        log_info: Log provider initialization info
        kg_provider: Optional pre-initialized provider to return directly
        client_config: Optional explicit MCE client config for oxp-api provider construction

    Returns:
        DataProvider instance or None on error
    """
    if kg_provider:
        return kg_provider

    if file:
        try:
            provider = JsonDataProvider(file)
            if log_info:
                logger.info(f"Using JSON Data Provider: {file}")
            return provider
        except Exception as e:
            logger.error(f"Error loading JSON file: {e}")
            return None

    if legacy:
        # Legacy ClickHouse API (backward compatibility with telemetry-hub)
        try:
            from mce.legacy.legacy_api_provider import LegacyApiProvider  # type: ignore[import]

            provider = LegacyApiProvider()
            if not provider._available:
                logger.error("Legacy ClickHouse API not available")
                return None
            if log_info:
                logger.info("Using Legacy ClickHouse API Provider")
            return provider
        except ImportError:
            logger.error("mce-legacy package not found")
            return None

    # Default: oxp-api provider. mce-client does not own any Neo4j adapter.

    provider = build_oxp_kg_provider(client_config)
    if provider and log_info:
        logger.info("Using OXPKGProvider (oxp-api)")
    return provider
