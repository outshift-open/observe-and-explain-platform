#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import datetime
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict

from dem.intelligence import InsightTemplateModel, load_templates_from_disk
from oxp_ontology.models.nodes.insight import Insight

logger = logging.getLogger(__name__)


def _render_template(template: str, variables: Dict[str, Any]) -> str:
    """Substitute $variable placeholders in template with values from variables dict."""
    if not template:
        return ""
    result = template
    for key, value in variables.items():
        result = result.replace(f"${key}", str(value))
    return result


def _build_insight(template: InsightTemplateModel, variables: Dict[str, Any]) -> Insight:
    """Render an insight template against a query result row into an Insight object."""
    name = _render_template(template.nameTemplate, variables)
    description = _render_template(template.descriptionTemplate, variables)
    priority = _render_template(template.priority, variables) if template.priority else None
    labels = [_render_template(label, variables) for label in getattr(template, "labels", [])]
    target_node_id = _render_template(template.targetNodeId, variables) if template.targetNodeId else None
    scope = getattr(template, "scope", None)

    insight_id = hashlib.sha256((template.templateId + (target_node_id or "") + name).encode()).hexdigest()
    created_at = datetime.datetime.now(datetime.timezone.utc)
    return Insight(
        id=insight_id,
        dataType="text",
        name=name,
        description=description,
        templateId=template.templateId,
        labels=json.dumps(labels),
        scope=scope or "",
        priority=priority or "",
        targetNodeId=target_node_id or "",
        createdAt=created_at,
    )


class IntelligenceWrapper:
    """Execute intelligence templates loaded from the versioned catalog."""

    def __init__(
        self,
        catalog_root: str,
        db_handler,
    ):
        if not catalog_root:
            raise ValueError("Missing intelligence catalog root path.")

        self.catalog_root = Path(catalog_root).expanduser().resolve()
        self.db_handler = db_handler
        self.templates = load_templates_from_disk(self.catalog_root)
        logger.info("Loaded %d insight templates from catalog.", len(self.templates))

    async def generate_insights(
        self,
        application_id: str,
        max_concurrency: int = 8,
    ) -> list[Insight]:
        if not self.templates:
            logger.info("No insight templates found in catalog, nothing to execute.")
            return []

        semaphore = asyncio.Semaphore(max(1, min(len(self.templates), max_concurrency)))

        async def _run_template_query(
            template: InsightTemplateModel,
        ) -> list[Insight]:
            insights: list[Insight] = []
            logger.info(f"Running query for template {template.templateId}")
            try:
                async with semaphore:
                    rows = await asyncio.to_thread(
                        self.db_handler.generate_insights_from_query,
                        template.kgQuery,
                        application_id,
                    )

                for variables in rows:
                    insights.append(_build_insight(template, variables))
            except Exception as exc:
                logger.warning(
                    "Insight template generator encountered an unexpected exception: %s",
                    exc,
                    exc_info=True,
                )
            return insights

        results = await asyncio.gather(*(_run_template_query(template) for template in self.templates))
        all_insights = [insight for insight_list in results for insight in insight_list]

        unique_insights_by_id: Dict[str, Insight] = {}
        for insight in all_insights:
            unique_insights_by_id[insight.id] = insight

        unique_insights = list(unique_insights_by_id.values())

        if unique_insights:
            await asyncio.to_thread(self.db_handler.ingest_insights, unique_insights)
            logger.info(
                "Ingested %d unique insights into the KG (generated rows=%d).",
                len(unique_insights),
                len(all_insights),
            )

        return unique_insights
