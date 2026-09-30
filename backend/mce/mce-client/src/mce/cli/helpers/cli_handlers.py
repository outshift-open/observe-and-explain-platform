#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
CLI Handler Utilities

Additional helper functions for CLI command handlers.
"""

from __future__ import annotations

import click


def handle_list_resources(kg_provider, scope: str, session_id: tuple | None = None):
    """
    Handle --list-resources flag for compute command.

    Args:
        kg_provider: Knowledge graph provider instance
        scope: Resource scope (session/agent/llm/task)
        session_id: Session ID tuple (if applicable)
    """
    from mce.cli.helpers import list_sessions, list_agents, list_llm_calls

    if not kg_provider:
        click.echo("Error: --list-resources requires Neo4j provider", err=True)
        return

    if scope == "session":
        sessions = list_sessions(kg_provider)
        click.echo(f"Available Sessions ({len(sessions)}):")
        for s in sessions:
            click.echo(f"  {s['session_id']} - {s.get('name', 'N/A')}")

    elif scope == "agent":
        if not session_id:
            click.echo("Error: --session-id required to list agents", err=True)
            return
        agents = list_agents(kg_provider, session_id[0])
        click.echo(f"Available Agents in session {session_id[0]} ({len(agents)}):")
        for a in agents:
            click.echo(f"  {a['agent_id']} - {a.get('name', 'N/A')}")

    elif scope == "llm":
        if not session_id:
            click.echo("Error: --session-id required to list LLM resources", err=True)
            return
        calls = list_llm_calls(kg_provider, session_id[0])
        click.echo(
            f"Available LLM Resources in session {session_id[0]} ({len(calls)}):"
        )
        for c in calls:
            call_id = c.get(
                "call_id", c.get("id", "N/A")
            )  # Handle both call_id and id keys
            model = c.get("model", "N/A")
            ts = c.get("timestamp", "")
            click.echo(f"  {call_id} - {model} ({ts})")

    else:
        click.echo(f"--list-resources for scope '{scope}' not yet implemented")
