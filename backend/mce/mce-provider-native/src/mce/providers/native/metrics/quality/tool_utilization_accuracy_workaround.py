#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

"""Temporary compatibility helpers for legacy ToolCall field names.

The canonical ontology shape for ToolCall metrics uses ``toolArguments`` and
``outputContent``. Until upstream normalization is corrected, this workaround
absorbs historical naming differences such as ``inputParams`` and
``toolOutput`` inside MCE, so the provider layer can remain a raw KG passthrough.

Convention
----------
This module is a metric-local workaround. It must only adapt already-fetched
metric context and must never trigger an additional KG query. Query-shape
fallbacks belong to oxp-api query builders and providers.
"""


def resolve_tool_call_fields(
    context: dict[str, Any],
) -> tuple[str, str, str, str, list[str]]:
    """WORKAROUND: accept canonical and legacy ToolCall field layouts.

    The canonical ontology shape uses ``toolArguments`` and ``outputContent``.
    Older payloads and intermediate provider normalizations may still expose
    ``inputParams`` or ``toolOutput`` instead.
    """
    tool_input = (
        context.get("toolArguments")
        or context.get("inputParams")
        or context.get("input_payload")
        or context.get("input_text")
        or ""
    )
    tool_output = (
        context.get("outputContent")
        or context.get("toolOutput")
        or context.get("output_payload")
        or context.get("output_text")
        or ""
    )
    tool_name = (
        context.get("toolName") or context.get("name") or context.get("tool_name") or ""
    )
    tool_definition = context.get("tool_definition") or context.get("tool_schema") or ""

    missing = [
        label
        for label, value in [
            ("toolArguments", tool_input),
            ("outputContent", tool_output),
            ("toolName", tool_name),
        ]
        if not value
    ]
    return (
        str(tool_input),
        str(tool_output),
        str(tool_name),
        str(tool_definition),
        missing,
    )
