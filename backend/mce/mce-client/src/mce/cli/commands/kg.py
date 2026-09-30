#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MCE CLI - Knowledge Graph Commands

Commands for interacting with the Knowledge Graph.
Delegates all KG I/O to mce.client — mce-core has no direct Neo4j dependency.
"""

from __future__ import annotations

import click
import json
import logging

from mce.client.config import MCEClientConfig
from mce.client.setup import build_oxp_kg_provider

logger = logging.getLogger(__name__)


def _get_kg_provider():
    """Instantiate a OXPKGProvider (oxp-api). Patchable in tests."""
    provider = build_oxp_kg_provider(MCEClientConfig.from_env())
    if provider is None:
        raise click.ClickException("oxp-api is required to build the KG provider")
    return provider


@click.group(name="kg")
def kg_group():
    """Interact with the Knowledge Graph directly."""


@kg_group.group(name="metric")
def metric_group():
    """Manage and inspect metrics in the Knowledge Graph."""


@metric_group.command(name="get")
@click.argument("entity_id", required=False)
@click.option("--metric-id", help="Filter by specific metric ID or name")
@click.option("--session-id", help="Scope query to a specific Session ID")
@click.option("--recursive", is_flag=True, help="Include metrics from child nodes")
@click.option("--provider", default="kg", help="Graph Provider")
def metric_get(entity_id, metric_id, session_id, recursive, provider):
    """List metrics attached to a specific Entity in the KG."""
    _handle_metric_command(entity_id, metric_id, session_id, recursive, mode="list")


@metric_group.command(name="show")
@click.argument("entity_id", required=False)
@click.option("--metric-id", help="Filter by specific metric ID or name")
@click.option("--session-id", help="Scope query to a specific Session ID")
@click.option("--recursive", is_flag=True, help="Include metrics from child nodes")
@click.option("--provider", default="kg", help="Graph Provider")
def metric_show(entity_id, metric_id, session_id, recursive, provider):
    """Show full details (JSON) of metrics attached to a specific Entity."""
    _handle_metric_command(entity_id, metric_id, session_id, recursive, mode="show")


@metric_group.command(name="compute")
@click.argument("metric_id")
@click.option("--entity-id", help="Target Entity ID")
@click.option("--session-id", required=True, help="Session Context (Required)")
@click.option(
    "--use-cache/--no-cache", default=True, help="Use existing value if available"
)
@click.option("--recursive", is_flag=True, help="Apply to all valid targets in session")
def metric_compute(metric_id, entity_id, session_id, use_cache, recursive):
    """Compute a metric for a specific entity or session via mce-client."""
    try:
        from mce.client import MCEWorkerService, WorkerConfig  # type: ignore[import]
        from mce.client.config import MCEClientConfig
    except ImportError:
        raise click.ClickException(
            "mce-client is required for compute. Install it first."
        )

    target = entity_id or session_id
    click.echo(f"Computing {metric_id} for {target}...")
    try:
        import tempfile
        import yaml as _yaml
        import pathlib

        # WorkerConfig only accepts a YAML file path — build a minimal one.
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
        _yaml.dump({"metrics": {"Session": [metric_id]}}, tmp)
        tmp.flush()
        cfg = WorkerConfig(pathlib.Path(tmp.name))
        svc = MCEWorkerService(
            config_path=cfg.path,
            client_config=MCEClientConfig.from_env(),
        )
        results = svc.process_session(target)
        click.echo(f"Done. {len(results)} result(s).")
        for r in results:
            click.echo(json.dumps(r, default=str, indent=2))
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


def _handle_metric_command(entity_id, metric_id, session_id, recursive, mode):
    """Shared handler for metric get/show — delegates to KG provider from mce-client."""
    if not entity_id and session_id:
        entity_id = session_id

    if not entity_id:
        click.echo("Error: Must provide ENTITY_ID or --session-id", err=True)
        return

    repo = _get_kg_provider()
    try:
        metrics = repo.get_metrics(
            entity_id,
            metric_ids=metric_id,
            recursive=recursive,
        )

        if not metrics:
            click.echo("No metrics found.")
            return

        if mode == "list":
            click.echo(f"Found {len(metrics)} metrics:")
            click.echo("-" * 140)
            click.echo(
                f"{'METRIC ID':<35} {'VALUE':<15} {'TIMESTAMP':<25} {'ENTITY ID':<35}"
            )
            click.echo("-" * 140)
            for m in metrics:
                val_str = str(m.value)[:15]
                ts = m.timestamp.isoformat() if m.timestamp else "N/A"
                rid = (m.resource_id or "")[:35]
                mid = str(m.metric_id or "")[:35]
                click.echo(f"{mid:<35} {val_str:<15} {ts:<25} {rid:<35}")

        elif mode == "show":
            for m in metrics:
                data = {
                    "metric_id": m.metric_id,
                    "value": m.value,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                    "entity_id": m.resource_id,
                }
                click.echo(json.dumps(data, indent=2))

    except Exception as e:
        click.echo(f"Error querying KG: {e}", err=True)
    finally:
        if hasattr(repo, "close"):
            repo.close()


@kg_group.command(name="query")
@click.option("--type", default="*", help="Entity Type/Label")
@click.option("--filter", "-f", multiple=True, help="Simple equality filter key=value")
@click.option("--limit", default=10, help="Max results")
def kg_query(type, filter, limit):
    """Query nodes in the KG (delegates to mce-client KG provider)."""
    repo = _get_kg_provider()
    try:
        filters_dict = {}
        for f in filter:
            if "=" in f:
                k, v = f.split("=", 1)
                filters_dict[k.strip()] = v.strip()

        if hasattr(repo, "query_nodes"):
            nodes = repo.query_nodes(type, filters_dict)
        elif hasattr(repo, "list_sessions"):
            nodes = repo.list_sessions(limit=limit)
        else:
            raise click.ClickException("KG provider does not support query_nodes.")

        click.echo(json.dumps(nodes, default=str, indent=2))
    except Exception as e:
        click.echo(f"Error: {e}")
    finally:
        if hasattr(repo, "close"):
            repo.close()
