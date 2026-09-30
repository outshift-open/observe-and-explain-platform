#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mce-client CLI — validate and inspect MCE worker configuration.

Entry point registered as ``mce-client`` in pyproject.toml.

Commands
--------
validate-config [CONFIG_PATH]   Validate a worker_config.yaml against the schema.
show-config     [CONFIG_PATH]   Print the resolved effective configuration.
show-schema                      Print the path to the bundled JSON Schema file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
import yaml

from .worker import WorkerConfig


@click.group()
@click.version_option(package_name="mce-client")
def app() -> None:
    """MCE Client — worker configuration utilities."""


@app.command("validate-config")
@click.argument(
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    required=False,
)
@click.option(
    "--schema",
    "show_schema_path",
    is_flag=True,
    default=False,
    help="Also print the path to the bundled JSON Schema file.",
)
def validate_config(config_path: Path | None, show_schema_path: bool) -> None:
    """Validate CONFIG_PATH against the worker_config JSON Schema.

    CONFIG_PATH defaults to the value of MCE_WORKER_CONFIG, or the bundled
    default config when neither is set.

    Exits with code 0 on success, 1 on validation failure.
    """
    if show_schema_path:
        click.echo(f"Schema: {WorkerConfig.SCHEMA_PATH}")

    try:
        cfg = WorkerConfig(config_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(click.style(f"✗  {exc}", fg="red"), err=True)
        sys.exit(1)

    source = config_path or cfg._path
    click.echo(click.style(f"✓  Config valid: {source}", fg="green"))
    click.echo(
        f"   engine: strategy={cfg.execution_strategy}, max_workers={cfg.max_workers}"
    )
    scopes = (
        ", ".join(f"{scope}={len(names)}" for scope, names in cfg.scope_metrics.items())
        or "none"
    )
    click.echo(f"   metrics: {scopes}")


@app.command("show-config")
@click.argument(
    "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    required=False,
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    default="yaml",
    show_default=True,
    help="Output format.",
)
def show_config(config_path: Path | None, fmt: str) -> None:
    """Print the resolved effective configuration.

    CONFIG_PATH defaults to MCE_WORKER_CONFIG or the bundled default.
    """
    try:
        cfg = WorkerConfig(config_path)
    except (FileNotFoundError, ValueError) as exc:
        click.echo(click.style(f"✗  {exc}", fg="red"), err=True)
        sys.exit(1)

    data = cfg.to_dict()
    if fmt == "json":
        click.echo(json.dumps(data, indent=2))
    else:
        click.echo(yaml.dump(data, default_flow_style=False, sort_keys=False).rstrip())


@app.command("show-schema")
def show_schema() -> None:
    """Print the path to the bundled JSON Schema file.

    The schema file enables IDE auto-completion (VS Code YAML extension) and
    serves as the authoritative field documentation.
    """
    click.echo(str(WorkerConfig.SCHEMA_PATH))


if __name__ == "__main__":
    app()
