#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
CLI Helper Modules

Extracted business logic from CLI commands to keep command files <100 LOC.
"""

from __future__ import annotations

from .metric_formatters import format_metric_list, format_metric_details
from .ontology_loader import load_ontology_hierarchy
from .compute_setup import (
    setup_llm_service,
    setup_data_provider,
    setup_cache_manager,
    setup_engine,
    select_and_resolve_metrics,
)
from .resource_lister import list_sessions, list_agents, list_llm_calls
from .cli_handlers import handle_list_resources

__all__ = [
    "format_metric_list",
    "format_metric_details",
    "load_ontology_hierarchy",
    "setup_llm_service",
    "setup_data_provider",
    "setup_cache_manager",
    "setup_engine",
    "select_and_resolve_metrics",
    "list_sessions",
    "list_agents",
    "list_llm_calls",
    "handle_list_resources",
]
