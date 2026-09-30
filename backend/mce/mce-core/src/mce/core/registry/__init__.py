#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
MCE Core Registry - Public API
==============================
Unified interface for metric discovery, registration and provider management.

This module provides:
- Metric discovery and registration
- Provider settings management
- Metric serialization for catalog export
- Backward compatibility with legacy API

Migrated from providers/catalog_legacy.py (2026-02-18)
"""

from __future__ import annotations

from typing import Any

# Alias for backward compatibility
from .service import MetricRegistry as Registry
from .discovery import discover_all_metrics, get_provider_name


def load_metrics_from_config(config: dict[str, Any]):
    """
    Load provider modules based on configuration.
    Example Config:
    {
      "providers": ["mce.providers.native", "mce.providers.deepeval"]
    }
    """
    registry = Registry.get_instance()

    # Load configured providers (native is already discovered via discover_all_metrics)
    providers = config.get("providers", [])
    for p in providers:
        registry.load_provider(p)


def get_default_metrics() -> list[Any]:
    """
    Returns the full catalog of available metric instances.

    Performs dynamic discovery across all enabled providers, resolves
    ontology applicability, and filters to latest versions.

    Returns:
        List of ready-to-use metric instances
    """
    return discover_all_metrics()


def serialize_metric_catalog_format(m, detailed: bool = False) -> dict:
    """
    Serializes a metric into the standard catalog JSON format.

    Args:
        m: Metric instance to serialize
        detailed: Include runtime fields (status, version, dependencies)

    Returns:
        Dictionary with catalog-compatible structure
    """
    md = m.metadata
    provider = get_provider_name(m)

    # Extract enum values safely
    layer_val = md.layer.value if hasattr(md.layer, "value") else str(md.layer)
    scope_val = md.scope.value if hasattr(md.scope, "value") else str(md.scope)
    nature_val = md.nature.value if hasattr(md.nature, "value") else str(md.nature)

    doc = {
        "Name": md.name or m.metric_id,
        "Description": md.description,
        "Layer": layer_val,
        "Scope": scope_val,
        "Provider": provider,
        "MCE Implemented": "Yes",
        "Nature": nature_val,
        "Ontology Class": md.ontology_class,
        "Is Virtual": getattr(m, "is_virtual", False),
    }

    if detailed:
        # Add runtime fields not present in static catalog
        doc.update(
            {
                "Status": (
                    "Available" if getattr(m, "is_available", True) else "Unavailable"
                ),
                "Version": getattr(md, "version", "N/A"),
                "Dependencies": getattr(m, "dependencies", []),
            }
        )

    return doc
