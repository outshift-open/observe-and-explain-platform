#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import click
import logging
import warnings
from dotenv import load_dotenv, find_dotenv

from .commands import metric_group, provider_group, kg_group, compute
from .commands.metric import (
    list_metrics,
    show_metric,
)  # For backward compatibility aliases

# Suppress Pydantic v1 compatibility warning from opik in Python 3.14+
# This must be done before any imports that trigger opik loading
warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater",
    category=UserWarning,
)

# Setup logging
# Default to WARNING to suppress noisy libraries (Neo4j, etc.)
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# Only load .env (search upwards from CWD)
load_dotenv(find_dotenv(usecwd=True))


@click.group()
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
@click.option(
    "-v", "--verbose", count=True, help="Enable verbose logging (-v: INFO, -vv: DEBUG)"
)
@click.option(
    "--env-file", type=click.Path(exists=True), help="Path to .env file to load"
)
def app(debug, verbose, env_file):
    """Metrics Computation Engine (MCE) CLI"""
    # Configure logging levels
    root_level = logging.WARNING

    if debug:
        root_level = logging.DEBUG
    elif verbose > 0:
        root_level = logging.INFO

    # Apply levels
    logging.getLogger().setLevel(root_level)

    # If not debug and not verbose:
    # 1. Silence external libraries (Neo4j, HTTPX)
    # 2. Keep MCE at WARNING level (only show errors/warnings by default)
    if not debug and verbose == 0:
        logging.getLogger("neo4j").setLevel(logging.ERROR)
        logging.getLogger("httpx").setLevel(logging.ERROR)
        logging.getLogger("httpcore").setLevel(logging.ERROR)
        logging.getLogger("mce").setLevel(logging.WARNING)  # Be quiet by default

    if verbose == 1:
        logging.getLogger("mce").setLevel(logging.INFO)
        # Don't enable INFO for everything else unless debug
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("neo4j").setLevel(logging.WARNING)

    if verbose >= 2:
        logging.getLogger("mce").setLevel(logging.DEBUG)
        logging.getLogger("neo4j").setLevel(logging.INFO)

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if env_file:
        load_dotenv(env_file, override=True)
        # click.echo(f"Loaded environment from {env_file}") # Keep CLI clean unless debug?


# Register Legacy Commands (optional — only available when mce-legacy is installed)
try:
    from mce.legacy.cli.legacy import legacy_cli  # type: ignore[import]

    app.add_command(legacy_cli)
except ImportError:
    pass

app.add_command(metric_group, name="metric")
app.add_command(provider_group, name="provider")
app.add_command(kg_group, name="kg")
app.add_command(compute)


# ==========================================
# Backward Compatibility Aliases
# ==========================================
@app.command(name="list-metrics", hidden=True)
@click.option("--provider")
def list_metrics_alias(provider):
    """Alias for 'mce metric list'"""
    ctx = click.get_current_context()
    ctx.invoke(list_metrics, provider=provider)


@app.command(name="show-metric", hidden=True)
@click.argument("metric_id")
def show_metric_alias(metric_id):
    """Alias for 'mce metric show'"""
    ctx = click.get_current_context()
    ctx.invoke(show_metric, metric_id=metric_id)


if __name__ == "__main__":
    app()
