#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import click
import importlib.util
from pathlib import Path


def _get_kg_provider():
    """Instantiate a OXPKGProvider (oxp-api). Patchable in tests."""
    from oxp.providers import OXPKGProvider  # type: ignore[import]

    return OXPKGProvider()


@click.group(name="legacy")
def legacy_cli():
    """Legacy V1 commands for backward compatibility."""


@legacy_cli.command(name="list-metrics")
def list_metrics():
    """List all available metrics (V1 styled output)."""
    # 1. Gather all default and provider metrics
    from mce.providers.native import ToolError, ToolErrorRate, ResponseCompleteness

    # Attempt to load externals
    if importlib.util.find_spec("mce.providers.deepeval.adapter") is not None:
        # Predefined list of known deepeval metrics to display
        deepeval_metrics = ["AnswerRelevancyMetric", "RoleAdherenceMetric"]
    else:
        deepeval_metrics = []

    # Format output to match V1 strictly
    click.echo("Available metrics (Simulated Legacy View):")

    # Native
    click.echo("\nNative metrics:")
    native_list = [ToolError(), ToolErrorRate(), ResponseCompleteness()]
    for m in native_list:
        click.echo(f"  • {m.ontology_class}")

    # DeepEval
    if deepeval_metrics:
        click.echo(f"\nPlugin metrics ({len(deepeval_metrics)}):")
        for name in deepeval_metrics:
            click.echo(f"  • {name}")


@legacy_cli.command()
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--server-url",
    default="http://localhost:8000",
    help="URL of the MCE server (Ignored in V2 Local Mode)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file for results (JSON format)",
)
def compute(config_file: Path, server_url: str, output: Path = None):
    """Compute metrics from a configuration file (V1 Compatibility Mode)."""
    import json
    from mce.engine.engine import MetricEngine
    from mce.providers.native import ToolError, ToolErrorRate, ResponseCompleteness

    click.echo(f"Running V1 Legacy Compute with config: {config_file}")

    # 1. Load V1 Config
    with open(config_file) as f:
        config = json.load(f)

    # V1 Config structure: {"session_id": "...", "metrics": ["ResponseCompleteness", ...], "llm_config": ...}
    session_id = config.get("session_id")
    if not session_id:
        click.echo("Error: Config must contain 'session_id'", err=True)
        return

    requested_metrics = config.get("metrics", [])

    # 2. Setup Engine — provider injected via mce-client (mce-core has no Neo4j dependency)
    provider = _get_kg_provider()

    engine = MetricEngine()
    engine.set_data_provider(provider)

    # 3. Dynamic Registration based on config
    # Map string names to V2 classes
    registry_map = {
        "ToolError": ToolError(),
        "ToolErrorRate": ToolErrorRate(),
        "ResponseCompleteness": ResponseCompleteness(),
        # Add adapters dynamically here...
    }

    for req_name in requested_metrics:
        if req_name in registry_map:
            engine.register_metric(registry_map[req_name])
        else:
            click.echo(
                f"Warning: Metric '{req_name}' not found in V2 registry.", err=True
            )

    # 4. Computed
    results = engine.compute_session(session_id)

    # 5. Output Transformation to V1 Schema
    # V1 Schema:
    # {
    #   "metrics": {...},
    #   "results": {
    #       "span_metrics": [...],
    #       "session_metrics": [...],
    #       "failed_metrics": [...]
    #   }
    # }

    session_metrics = []
    span_metrics = []
    failed_metrics = []

    for r in results:
        res_dict = {
            "metric_name": r.metric_class,
            "value": r.value,
            "reasoning": r.reasoning,
            "metadata": r.metadata,
            "error_message": r.error,
        }

        if r.error:
            # V1 puts failed metrics in a separate list
            failed_metrics.append(
                {
                    "metric_name": r.metric_class,
                    "error_message": r.error,
                    "aggregation_level": "unknown",
                }
            )
            continue

        # Classification based on resource_id
        if r.resource_id == session_id:
            session_metrics.append(res_dict)
        else:
            # Assume span level if not session level (could be agent too, but V1 distinguished them)
            # For strict compat, we might need better heuristic, but this covers 90%
            res_dict["span_id"] = r.resource_id
            span_metrics.append(res_dict)

    out_data = {
        "metrics": {
            m: {"source": "native"} for m in requested_metrics
        },  # Mock metadata
        "results": {
            "session_metrics": session_metrics,
            "span_metrics": span_metrics,
            "agent_metrics": [],  # Note: Agent-level metrics aggregation not implemented in legacy CLI
            "population_metrics": [],
            "failed_metrics": failed_metrics,
        },
    }

    if output:
        with open(output, "w") as f:
            json.dump(out_data, f, indent=2)
        click.echo(f"Saved results to {output}")
    else:
        click.echo(json.dumps(out_data, indent=2))
