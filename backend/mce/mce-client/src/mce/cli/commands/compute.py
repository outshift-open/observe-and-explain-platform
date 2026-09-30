#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MCE CLI - Compute Command (Refactored)

Main command for computing metrics on sessions.
Delegates setup logic to cli.helpers modules.
"""

from __future__ import annotations

import click
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _compute_via_worker_service(
    *,
    session_ids: list[str],
    worker_config: str | None,
    cache_read: bool,
    cache_write: bool,
    log_info: bool,
) -> None:
    from mce.client.config import MCEClientConfig
    from mce.client.worker import MCEWorkerService

    svc = MCEWorkerService(
        config_path=Path(worker_config) if worker_config else None,
        client_config=MCEClientConfig.from_env(),
        cache_read=cache_read,
        cache_write=cache_write,
    )

    cfg_path = worker_config or str(svc.config.path)
    if log_info:
        click.echo(f"Workflow path enabled via worker config: {cfg_path}")

    for sid in session_ids:
        if log_info:
            click.echo(f"Computing workflow metrics for session: {sid}")
        try:
            results = svc.process_session(sid)
            if log_info:
                click.echo(
                    f"Workflow computation complete for {sid}. Found {len(results)} results."
                )
            for res in results:
                click.echo(
                    f"  [{res.get('metric_id') or res.get('metric_name')}] "
                    f"{res.get('value')} ({res.get('reasoning')})"
                )
            if log_info:
                click.echo("-" * 40)
        except Exception:
            logger.exception("Workflow-path computation failed for %s", sid)
            click.echo(
                f"Computation Failed for {sid}: see logs for traceback", err=True
            )


@click.command()
@click.option(
    "--session-id", "-s", multiple=True, help="Session ID(s) to compute metrics for"
)
@click.option("--file", help="Path to JSON file containing session traces.")
@click.option("--legacy", is_flag=True, help="Use legacy ClickHouse API provider")
@click.option(
    "--metric", "-m", multiple=True, help="Metric to compute (REQUIRED unless --all)"
)
@click.option(
    "--all", "compute_all", is_flag=True, help="Compute ALL available metrics"
)
@click.option(
    "--scope",
    type=click.Choice(["session", "agent", "task", "llm"], case_sensitive=False),
    default=None,
    help="Resource scope",
)
@click.option("--resource-id", help="Specific resource ID (agent ID, task ID)")
@click.option("--list-resources", is_flag=True, help="List available resources")
@click.option(
    "--recursive", "-r", is_flag=True, help="Recursively compute for child resources"
)
@click.option(
    "--llm-mode",
    type=click.Choice(["live", "record", "replay", "error"], case_sensitive=False),
    default="live",
    help="LLM mode: live (call API), replay (cache only), record (call+save), error (raise on any call — for tests)",
)
@click.option(
    "--llm-cache", default=None, help="LLM cache file (required for replay/record mode)"
)
@click.option(
    "--cache-read/--no-cache-read",
    default=False,
    help="Read from KG metric cache (disabled by default)",
)
@click.option(
    "--cache-write/--no-cache-write",
    default=False,
    help="Write computed metrics back to KG (disabled by default)",
)
@click.option(
    "--workflow-path/--engine-path",
    default=False,
    help="Use MCEWorkerService like the workflow instead of calling MetricEngine directly.",
)
@click.option(
    "--worker-config",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Worker config YAML used with --workflow-path. Defaults to MCE_WORKER_CONFIG or the bundled worker config.",
)
def compute(
    session_id: tuple = (),
    file: str | None = None,
    legacy: bool = False,
    metric: tuple = (),
    compute_all: bool = False,
    scope: str | None = None,
    resource_id: str | None = None,
    list_resources: bool = False,
    recursive: bool = False,
    llm_mode: str = "live",
    llm_cache: str | None = None,
    cache_read: bool = False,
    cache_write: bool = False,
    workflow_path: bool = False,
    worker_config: str | None = None,
):
    """Compute metrics for a session (or file) using MCE v2 Engine"""
    from mce.cli.helpers import (
        setup_llm_service,
        setup_data_provider,
        setup_cache_manager,
        setup_engine,
        select_and_resolve_metrics,
        handle_list_resources,
    )

    log_info = logging.getLogger().isEnabledFor(logging.INFO)

    # Configure LLM
    setup_llm_service(llm_cache, llm_mode)

    if workflow_path:
        unsupported = []
        if file:
            unsupported.append("--file")
        if legacy:
            unsupported.append("--legacy")
        if scope is not None:
            unsupported.append("--scope")
        if resource_id is not None:
            unsupported.append("--resource-id")
        if list_resources:
            unsupported.append("--list-resources")
        if recursive:
            unsupported.append("--recursive")
        if unsupported:
            click.echo(
                "Error: --workflow-path does not support " + ", ".join(unsupported),
                err=True,
            )
            return

        if metric or compute_all:
            click.echo(
                "Warning: --metric/--all are ignored with --workflow-path; worker config controls the metric set.",
                err=True,
            )

        if not session_id:
            click.echo("Error: --session-id is required with --workflow-path", err=True)
            return

        _compute_via_worker_service(
            session_ids=list(session_id),
            worker_config=worker_config,
            cache_read=cache_read,
            cache_write=cache_write,
            log_info=log_info,
        )
        return

    # Initialize Data Provider
    data_provider = setup_data_provider(file=file, legacy=legacy, log_info=log_info)
    if not data_provider:
        click.echo("Error: Failed to initialize data provider.", err=True)
        return

    # Get KG provider reference for resource listing and saving.
    # Duck-typing: any provider with list_sessions() and save_metrics() qualifies.
    kg_provider = data_provider if hasattr(data_provider, "list_sessions") else None

    # Setup Cache
    cache_manager = setup_cache_manager(
        kg_provider,
        no_cache_read=not cache_read,
        no_cache_write=not cache_write,
    )

    # Setup Engine
    engine = setup_engine(data_provider, cache_manager)

    # Handle --list-resources
    if list_resources:
        handle_list_resources(kg_provider, scope, session_id)
        return

    # Validate session_id when computing
    if not file and not session_id:
        click.echo("Error: --session-id is required when not using --file", err=True)
        return

    # Validate metric selection
    if not metric and not compute_all:
        click.echo(
            "Error: Must specify metrics with -m <metric_id> or use --all flag",
            err=True,
        )
        click.echo("Use 'mce metric list' to see available metrics")
        return

    # Select and resolve metrics with dependencies
    selected_metrics, error = select_and_resolve_metrics(
        list(metric), compute_all=compute_all, log_info=log_info
    )
    if error:
        click.echo(f"Error: {error}", err=True)
        return

    # Register metrics with engine
    for m in selected_metrics:
        engine.register_metric(m)

    # Auto-enable recursive mode only when CLI --scope is explicitly set
    # (computing on llm/tool/agent/task requires traversing session hierarchy)
    # NOTE: Do NOT auto-enable based on metric metadata scope - polymorphic metrics
    # like AnswerRelevancy apply to both Session and LLMCall levels. Without --scope,
    # we compute at session level only (1 value).
    if not recursive and scope is not None and scope != "session":
        recursive = True
        if log_info:
            click.echo(f"Auto-enabled recursive mode for scope '{scope}'")

    # Determine sessions to process
    sessions_to_process = list(session_id) if session_id else []
    if file and not sessions_to_process:
        if hasattr(data_provider, "list_session_ids"):
            sessions_to_process = data_provider.list_session_ids()
        else:
            click.echo("Error: Provider does not support listing sessions", err=True)
            return

    # Execute computation
    for sid_raw in sessions_to_process:
        # Resolve Session ID if provider supports it (handling sub-resources passed as session-id)
        sid = sid_raw
        target_rid = resource_id  # Default to CLI argument
        effective_recursive = recursive  # per-iteration copy; never mutate outer var

        if hasattr(data_provider, "resolve_session_id"):
            resolved = data_provider.resolve_session_id(sid_raw)
            if resolved and resolved != sid:
                if log_info:
                    click.echo(f"Resolved resource '{sid_raw}' -> Session '{resolved}'")
                sid = resolved

                # If target resource was not specified, assume the user meant to target this specific resource
                if not target_rid:
                    target_rid = sid_raw
                    if log_info:
                        click.echo(
                            f"Implicitly targeting resource: {target_rid} (derived from --session-id)"
                        )
                    # Targeting a sub-resource requires recursive mode to build span batches
                    if not effective_recursive:
                        effective_recursive = True
                        if log_info:
                            click.echo(
                                "Auto-enabled recursive mode to reach sub-resource"
                            )

        if log_info:
            click.echo(f"Computing metrics for session: {sid}")
        try:
            results = engine.compute_session(
                sid,
                recursive=effective_recursive,
                target_resource_id=target_rid,
                scope=scope,
            )

            # Results are persisted by KnowledgeGraphCache.store() during compute.
            # No explicit save_metrics() call needed here.

            # Display results
            if log_info:
                click.echo(
                    f"Computation Complete for {sid}. Found {len(results)} results."
                )

            for res in results:
                click.echo(f"  [{res.display_name}] {res.value} ({res.reasoning})")

            if log_info:
                click.echo("-" * 40)
        except Exception:
            logger.exception("Engine-path computation failed for %s", sid)
            click.echo(
                f"Computation Failed for {sid}: see logs for traceback", err=True
            )
