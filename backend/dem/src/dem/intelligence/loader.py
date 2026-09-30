#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
import logging
import re
from pathlib import Path
from typing import List

from dem.intelligence.template_model import InsightTemplateModel


logger = logging.getLogger(__name__)

# Allowed execution scope values
ALLOWED_SCOPES = {"Session", "Agent", "MAS", "SemanticGroup"}


def _extract_template_variables(text: str) -> set[str]:
    """Extract placeholder variables from template fields."""
    if not text:
        return set()
    dollar_vars = set(re.findall(r"\$([A-Za-z_]\w*)", text))
    return dollar_vars


def _split_top_level_csv(text: str) -> list[str]:
    """Split a Cypher expression list by top-level commas only."""
    items: list[str] = []
    current: list[str] = []
    depth_paren = 0
    depth_bracket = 0
    depth_brace = 0
    in_single_quote = False
    in_double_quote = False

    for ch in text:
        if ch == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
            current.append(ch)
            continue
        if ch == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
            current.append(ch)
            continue

        if not in_single_quote and not in_double_quote:
            if ch == "(":
                depth_paren += 1
            elif ch == ")":
                depth_paren = max(0, depth_paren - 1)
            elif ch == "[":
                depth_bracket += 1
            elif ch == "]":
                depth_bracket = max(0, depth_bracket - 1)
            elif ch == "{":
                depth_brace += 1
            elif ch == "}":
                depth_brace = max(0, depth_brace - 1)
            elif (
                ch == ","
                and depth_paren == 0
                and depth_bracket == 0
                and depth_brace == 0
            ):
                part = "".join(current).strip()
                if part:
                    items.append(part)
                current = []
                continue

        current.append(ch)

    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _extract_returned_variables(kg_query: str) -> set[str]:
    """Extract returned variable names/aliases from a Cypher RETURN clause."""
    if not kg_query:
        return set()

    return_match = re.search(
        r"\bRETURN\b(?P<body>.*?)(?:\bORDER\s+BY\b|\bLIMIT\b|\bSKIP\b|$)",
        kg_query,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not return_match:
        return set()

    body = return_match.group("body").strip()
    if not body:
        return set()

    returned_vars: set[str] = set()
    for item in _split_top_level_csv(body):
        alias_match = re.search(r"\bAS\s+([A-Za-z_]\w*)\s*$", item, flags=re.IGNORECASE)
        if alias_match:
            returned_vars.add(alias_match.group(1))
            continue

        property_match = re.search(r"([A-Za-z_]\w*)\.([A-Za-z_]\w*)\s*$", item)
        if property_match:
            returned_vars.add(property_match.group(2))
            continue

        bare_var_match = re.search(r"^([A-Za-z_]\w*)$", item)
        if bare_var_match:
            returned_vars.add(bare_var_match.group(1))

    return returned_vars


def _validate_template(template: InsightTemplateModel, path: Path) -> bool:
    """Validate template scope and variable references.

    Args:
        template: The InsightTemplateModel to validate.
        path: The source file path (for logging).

    Returns:
        True if valid, False if invalid (error is logged).
    """
    # 1. Validate scope is in allowed values
    if template.scope and template.scope not in ALLOWED_SCOPES:
        logger.error(
            "Invalid scope '%s' in template %s. Must be one of: %s",
            template.scope,
            path.name,
            ", ".join(sorted(ALLOWED_SCOPES)),
        )
        return False

    # 2. Validate variable references
    # Extract all placeholder variables from template fields
    template_vars = set()
    template_vars.update(_extract_template_variables(template.nameTemplate))
    template_vars.update(_extract_template_variables(template.descriptionTemplate))
    if template.labels:
        for label in template.labels:
            template_vars.update(_extract_template_variables(label))
    if template.targetNodeId:
        template_vars.update(_extract_template_variables(template.targetNodeId))
    if template.priority:
        template_vars.update(_extract_template_variables(template.priority))

    # Extract returned variables from the kgQuery RETURN clause
    query_vars = _extract_returned_variables(template.kgQuery)

    # Check if all template placeholders are present in query RETURN variables
    undefined_vars = template_vars - query_vars - {"application_id"}
    if undefined_vars:
        logger.error(
            "Template placeholders %s in template %s are not returned by kgQuery. "
            "Available RETURN variables: %s",
            sorted(undefined_vars),
            path.name,
            sorted(query_vars) if query_vars else "(none)",
        )
        return False

    return True


def load_templates_from_disk(
    catalog_root: Path,
) -> List[InsightTemplateModel]:
    """Parse every JSON file under <catalog_root>/insight-templates/."""
    templates_dir = catalog_root / "insight-templates"
    if not templates_dir.exists():
        logger.warning("insight-templates directory not found at %s", templates_dir)
        return []

    nodes = []
    for path in sorted(templates_dir.rglob("*.json")):
        try:
            with path.open() as f:
                data = json.load(f)
            node = InsightTemplateModel(
                nameTemplate=data["nameTemplate"],
                descriptionTemplate=data["descriptionTemplate"],
                kgQuery="\n".join(data["kgQuery"])
                if isinstance(data["kgQuery"], list)
                else data["kgQuery"],
                labels=data.get("labels", []),
                scope=data.get("scope"),
                priority=data.get("priority"),
                targetNodeId=data.get("targetNodeId"),
            )

            # Validate the template before adding
            if not _validate_template(node, path):
                logger.warning("Skipping invalid template %s", path.name)
                continue

            nodes.append(node)
            logger.debug("Loaded template '%s' from %s", node.nameTemplate, path.name)
        except (KeyError, json.JSONDecodeError) as exc:
            logger.error("Failed to parse insight template %s: %s", path, exc)

    return nodes
