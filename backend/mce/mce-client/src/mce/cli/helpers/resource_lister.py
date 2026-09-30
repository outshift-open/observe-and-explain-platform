#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Resource Listing Utilities

Functions for listing KG resources (sessions, agents, LLM calls).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def list_sessions(kg_provider) -> list[dict[str, Any]]:
    """
    List available sessions in the Knowledge Graph.

    Args:
        kg_provider: Knowledge graph provider instance

    Returns:
        List of session dictionaries with id, name, timestamp
    """
    try:
        return kg_provider.list_sessions()
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        return []


def list_agents(kg_provider, session_id: str) -> list[dict[str, Any]]:
    """
    List agents (AgentCalls) in a given session.

    Args:
        kg_provider: Knowledge graph provider instance
        session_id: Session identifier

    Returns:
        List of agent dictionaries with agent_id, name, agent_type
    """
    try:
        return kg_provider.list_agents(session_id)
    except Exception as e:
        logger.error(f"Error listing agents for session {session_id}: {e}")
        return []


def list_llm_calls(kg_provider, session_id: str) -> list[dict[str, Any]]:
    """
    List LLM resources/spans in a given session.

    Args:
        kg_provider: Knowledge graph provider instance
        session_id: Session identifier

    Returns:
        List of LLM call dictionaries with id, model, timestamp
    """
    try:
        if hasattr(kg_provider, "list_llm_calls"):
            return kg_provider.list_llm_calls(session_id)
        else:
            logger.warning(
                "Listing LLM resources not supported by this provider version."
            )
            return []
    except Exception as e:
        logger.error(f"Error listing LLM calls for session {session_id}: {e}")
        return []
