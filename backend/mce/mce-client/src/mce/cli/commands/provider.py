#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MCE CLI - Provider Commands

Commands for inspecting metric providers.
"""

from __future__ import annotations

import click


@click.group(name="provider")
def provider_group():
    """Inspect metric providers."""


@provider_group.command(name="list")
def list_providers():
    """List detected providers and their metric counts."""
    from mce.core.registry import get_default_metrics, get_provider_name
    from collections import defaultdict

    all_metrics = get_default_metrics()
    provider_metrics: dict = defaultdict(int)
    for metric in all_metrics:
        provider_metrics[get_provider_name(metric)] += 1

    click.echo(f"{'PROVIDER':<15} {'METRICS':<8} {'STATUS'}")
    click.echo("-" * 50)
    for provider in sorted(provider_metrics):
        count = provider_metrics[provider]
        click.echo(f"{provider:<15} {count:<8} OK")
