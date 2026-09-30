#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Metric Formatting Utilities

Functions for formatting metric catalog data for CLI display.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def format_metric_list(
    metrics: list[Any], json_output: bool = False, show_abstract: bool = False
) -> str:
    """
    Format metric list for CLI display.

    Args:
        metrics: List of metric instances or contracts
        json_output: If True, return JSON string
        show_abstract: If True, format as abstract definitions

    Returns:
        Formatted string for CLI output
    """
    from mce.core.registry import get_provider_name

    if json_output:
        from mce.core.registry import serialize_metric_catalog_format

        data = [serialize_metric_catalog_format(m, detailed=True) for m in metrics]
        return json.dumps(data, indent=2)

    if show_abstract:
        # Abstract definitions (contracts)
        lines = [f"{'METRIC ID':<30} {'LAYER':<15} {'SCOPE':<10} DESCRIPTION"]
        lines.append("-" * 80)
        for m in metrics:
            md = m.metadata if hasattr(m, "metadata") else m
            desc = (
                (md.description[:37] + "...")
                if len(md.description) > 40
                else md.description
            )
            display = (
                md.get_display_name() if hasattr(md, "get_display_name") else md.name
            )
            lines.append(
                f"{display:<30} {md.layer.value:<15} {md.scope.value:<10} {desc}"
            )
        return "\n".join(lines)

    # Implementation list
    lines = [f"{'METRIC NAME':<35} {'PROVIDER':<10} {'SCOPE':<50} {'STATUS':<10}"]
    lines.append("-" * 110)

    for m in metrics:
        prov = get_provider_name(m)
        is_avail = getattr(m, "is_available", True)
        status = "OK" if is_avail else "N/A"

        scope_str = m.metadata.scope.value
        if scope_str == "ExecutionElement":
            scope_str = "Session, MASCall, AgentCall, LLMCall, ToolCall"

        display = m.metadata.get_display_name()
        lines.append(f"{display:<35} {prov:<10} {scope_str:<50} {status:<10}")

    return "\n".join(lines)


def format_metric_details(
    metric_id: str, contract: Any = None, implementations: list[Any] = None
) -> str:
    """
    Format detailed metric information for CLI display.

    Args:
        metric_id: Metric identifier
        contract: Abstract contract (base class) if available
        implementations: List of metric implementations

    Returns:
        Formatted string with full metric details
    """
    from mce.core.registry import get_provider_name

    lines = []

    # ========================================================================
    # METADATA TABLE (Key: Value format)
    # ========================================================================
    if contract:
        if isinstance(contract, type):
            md = contract.metadata
            display = (
                md.get_display_name() if hasattr(md, "get_display_name") else md.name
            )
            lines.append(f"Abstract Metric: {display}")
        else:
            md = contract.metadata
            display = (
                md.get_display_name() if hasattr(md, "get_display_name") else md.name
            )
            lines.append(f"Metric: {display}")
    elif implementations:
        # Use first implementation's metadata if no contract
        md = implementations[0].metadata
        display = md.get_display_name() if hasattr(md, "get_display_name") else md.name
        lines.append(f"Metric: {display}")
    else:
        lines.append(f"Metric: {metric_id}")
        lines.append("\nNo metadata available.")
        return "\n".join(lines)

    lines.append(f"{'=' * 80}")
    lines.append("\nMetadata:")
    lines.append(f"{'-' * 80}")

    # Format as key: value table
    metadata_rows = []
    metadata_rows.append(("Description", md.description))
    metadata_rows.append(("Layer", md.layer.value))

    scope_value = md.scope.value
    if scope_value == "ExecutionElement":
        scope_value = (
            "ExecutionElement (Session, MASCall, AgentCall, LLMCall, ToolCall)"
        )
    metadata_rows.append(("Scope", scope_value))

    metadata_rows.append(("Nature", md.nature.value))

    if hasattr(md, "ontology_class") and md.ontology_class:
        metadata_rows.append(("Ontology Class", md.ontology_class))

    if hasattr(md, "attachment_point") and md.attachment_point:
        metadata_rows.append(("Attachment Point", md.attachment_point))

    if hasattr(md, "target_types") and md.target_types:
        target_types_str = ", ".join(sorted(md.target_types))
        metadata_rows.append(("Target Types", target_types_str))

    if hasattr(md, "version") and md.version:
        metadata_rows.append(("Version", md.version))

    # Calculate max key width
    max_key_width = max(len(row[0]) for row in metadata_rows)

    # Print table
    for key, value in metadata_rows:
        lines.append(f"  {key:<{max_key_width}} : {value}")

    # Show input requirements from contract if available
    if contract and not isinstance(contract, type):
        reqs = contract.input_requirements
        req_lines = []
        if reqs.required_entities:
            req_lines.append(f"Required Entities: {', '.join(reqs.required_entities)}")
        if reqs.text_fields:
            req_lines.append(f"Text Fields: {', '.join(reqs.text_fields)}")
        if reqs.vector_fields:
            req_lines.append(f"Vector Fields: {', '.join(reqs.vector_fields)}")
        if reqs.scalar_fields:
            req_lines.append(f"Scalar Fields: {', '.join(reqs.scalar_fields)}")

        if req_lines:
            lines.append(
                f"\n  {'Input Requirements':<{max_key_width}} : {req_lines[0]}"
            )
            for req_line in req_lines[1:]:
                lines.append(f"  {'':<{max_key_width}}   {req_line}")

    # ========================================================================
    # IMPLEMENTATIONS TABLE
    # ========================================================================
    if implementations:
        lines.append(f"\n{'=' * 80}")
        lines.append("\nImplementations:")
        lines.append(f"{'-' * 80}")

        # Table header
        lines.append(f"{'IMPLEMENTATION':<40} {'PROVIDER':<12} {'STATUS':<18}")
        lines.append(f"{'-' * 72}")

        # Table rows
        for impl in implementations:
            provider = get_provider_name(impl)
            is_avail = getattr(impl, "is_available", True)
            status = "✓ Available" if is_avail else "✗ Unavailable"

            display = impl.metadata.get_display_name()
            lines.append(f"{display:<40} {provider:<12} {status:<18}")

            # Show dependencies if present (indented below)
            if hasattr(impl, "dependencies") and impl.dependencies:
                deps_str = ", ".join(impl.dependencies)
                lines.append(f"  └─ Dependencies: {deps_str}")

            # Show error if unavailable
            if not is_avail:
                err = getattr(impl, "_availability_error", "Unknown Error")
                lines.append(f"  └─ Error: {err}")
    else:
        lines.append(f"\n{'=' * 80}")
        lines.append("\nNo implementations found.")
        lines.append("This is an abstract metric definition only.")

    return "\n".join(lines)
