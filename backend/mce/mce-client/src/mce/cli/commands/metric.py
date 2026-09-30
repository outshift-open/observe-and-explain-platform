#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MCE CLI - Metric Commands (Refactored)

Commands for managing and inspecting metrics.
Delegates business logic to cli.helpers modules.
"""

from __future__ import annotations

import click
import json


@click.group(name="metric")
def metric_group():
    """Manage and inspect metrics."""


@metric_group.command(name="list")
@click.option("--provider", help="Filter by provider (e.g. native, deepeval, opik)")
@click.option("--all", "show_all", is_flag=True, help="Include unavailable metrics")
@click.option("--abstract", is_flag=True, help="List only abstract metric definitions")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def list_metrics(provider, show_all, abstract, json_output):
    """List all available metrics registered in default configuration."""
    from mce.core.registry import get_default_metrics, get_provider_name
    from mce.cli.helpers import format_metric_list

    if abstract:
        from mce.core.specs import SpecRegistry

        specs = SpecRegistry.all_specs()

        if json_output:
            click.echo(json.dumps([s.to_dict() for s in specs], indent=2))
            return

        header = f"{'NAME':<42} {'LAYER':<12} {'NATURE':<16} {'SCOPE':<20} VERSION"
        sep = "-" * len(header)
        lines = [header, sep]
        for s in specs:
            lines.append(
                f"{s.name:<42} {s.layer.value:<12} {s.nature.value:<16}"
                f" {s.scope.value:<20} {s.version}"
            )
        lines.append(f"\n{len(specs)} specs total.")
        click.echo("\n".join(lines))
        return

    # List Implementations
    all_impls = get_default_metrics()

    # Filter by Provider
    if provider:
        p_lower = provider.lower()
        all_impls = [m for m in all_impls if get_provider_name(m).lower() == p_lower]

    # Filter by Availability
    if not show_all:
        all_impls = [m for m in all_impls if getattr(m, "is_available", True)]

    output = format_metric_list(all_impls, json_output=json_output, show_abstract=False)
    click.echo(output)


@metric_group.command(name="show")
@click.argument("metric_id")
def show_metric(metric_id: str):
    """Show comprehensive details for a specific metric."""
    from mce.core.registry import get_default_metrics
    from mce.core.catalog import MetricCatalogService
    from mce.cli.helpers import format_metric_details
    from mce.cli.helpers.compute_setup import parse_templated_metric
    from mce.core.types import normalize_metric_id

    # Parse templated syntax (Avg<X>, Aggregate<op, X>)
    metric_id = parse_templated_metric(metric_id)

    # Normalize for backward compatibility
    metric_id_normalized = normalize_metric_id(metric_id)

    # 1. Look up the canonical spec first (pure-data descriptor, fastest path)
    from mce.core.specs import SpecRegistry

    spec = SpecRegistry.get(metric_id_normalized)

    # Fall back to the catalog for virtual / lazily-loaded aggregate metrics
    # that have no corresponding spec file (e.g. "avg_AnswerRelevancy").
    catalog = MetricCatalogService.get_instance()
    contract = spec
    if contract is None:
        contract = catalog.get_contract(metric_id_normalized)

    # 2. Get all implementations
    metrics = get_default_metrics()
    implementations = []
    for m in metrics:
        m_id_normalized = normalize_metric_id(m.metric_id)
        if m.metric_id == metric_id or m_id_normalized == metric_id_normalized:
            implementations.append(m)

    # 3. OPTION C: Lazy loading fallback for templated aggregates
    # If no implementations found, try catalog.get_metric() for lazy-loaded metrics
    if not implementations:
        lazy_metric = catalog.get_metric(metric_id_normalized)
        if lazy_metric:
            implementations.append(lazy_metric)

    # If no contract and no implementations found
    if not contract and not implementations:
        click.echo(f"Metric '{metric_id}' not found.")
        return

    output = format_metric_details(
        metric_id, contract=contract, implementations=implementations
    )
    click.echo(output)


@metric_group.command(name="export")
@click.argument("format", type=click.Choice(["json"]), default="json")
@click.argument("output_file", type=click.Path())
def export_metrics(format, output_file):
    """Export the metric catalog to a file (JSON)."""
    from mce.core.registry import get_default_metrics, serialize_metric_catalog_format

    metrics = get_default_metrics()
    data = [serialize_metric_catalog_format(m, detailed=False) for m in metrics]

    with open(output_file, "w") as f:
        if format == "json":
            json.dump(data, f, indent=2)

    click.echo(f"Exported {len(data)} metrics to {output_file}")
