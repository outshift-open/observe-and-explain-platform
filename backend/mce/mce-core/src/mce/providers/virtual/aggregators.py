#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any, Callable
import statistics
from mce.core.metric import (
    Metric,
    MetricMetadata,
    MetricLayer,
    MetricNature,
    MetricScope,
    MetricRequirements,
)
from mce.core.metadata import MetricImplementationType
from mce.core.types import MetricResult
import logging

logger = logging.getLogger(__name__)


class VirtualMetric(Metric):
    """
    Base class for Virtual Metrics (aggregations/transformations of other metrics).
    Virtual metrics are always recomputed and never persisted to cache.
    """

    @property
    def is_virtual(self) -> bool:
        return True


class AggregateMetric(VirtualMetric):
    """
    Generic templated metric: Aggregate<Operation, TargetMetric>

    This is a meta-metric that applies an aggregation operation to results
    of a target metric across multiple resources.

    Examples:
        - Average<AnswerRelevancy> → avg_AnswerRelevancy
        - Max<LLMConfidence> → max_LLMConfidence
        - Sum<TokenCount> → sum_TokenCount

    Architecture:
        AverageMetric is a special case: Aggregate<Avg, Metric>
    """

    def __init__(
        self,
        target_metric_id: str,
        operation_name: str,
        operation_fn: Callable[[list[float]], float],
        ontology_class: str = "Session",
    ):
        """
        Args:
            target_metric_id: The base metric to aggregate (e.g., "AnswerRelevancy")
            operation_name: Name of operation (e.g., "avg", "max", "sum")
            operation_fn: Function that takes list of values and returns aggregated value
            ontology_class: Ontology class for the aggregated metric
        """
        self.target_metric = target_metric_id
        self.operation_name = operation_name
        self.operation_fn = operation_fn

        self.metadata = MetricMetadata(
            name=f"{operation_name}_{target_metric_id}",
            description=f"{operation_name.capitalize()} of {target_metric_id} over scope",
            layer=MetricLayer.AGGREGATION,  # Virtual layer
            nature=MetricNature.DETERMINISTIC,
            scope=MetricScope.SESSION,
            ontology_class=ontology_class,
            dependencies=[target_metric_id],
            implementation_type=MetricImplementationType.VIRTUAL,
        )

    @property
    def input_requirements(self):
        return MetricRequirements()

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        """
        Aggregate results from computed_metrics context.

        The engine populates ``context['computed_metrics']`` with all MetricResult
        objects computed so far (via ContextBuilder.update_contexts_with_results).
        """
        # Collect all MetricResult objects injected by the engine
        all_results = context.get("computed_metrics", [])
        if not isinstance(all_results, list):
            all_results = []

        # Filter for target metric
        values = [
            r.value
            for r in all_results
            if isinstance(r, MetricResult)
            and r.metric_id == self.target_metric
            and isinstance(r.value, (int, float))
        ]
        logger.debug(
            "AggregateMetric(%s): found %d results for target '%s'",
            self.metric_id,
            len(values),
            self.target_metric,
        )

        if not values:
            logger.warning(
                "AggregateMetric(%s): no %s results in context for resource %s "
                "(check that the base metric ran before the aggregate)",
                self.metric_id,
                self.target_metric,
                resource_id,
            )
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="virtual",
                value=0.0,
                reasoning=f"No results found for {self.target_metric}",
                metadata={"count": 0, "operation": self.operation_name},
            )

        # Apply aggregation operation
        aggregated_value = float(self.operation_fn(values))

        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="virtual",
            value=aggregated_value,
            reasoning=f"{self.operation_name.capitalize()} of {len(values)} results",
            metadata={
                "count": len(values),
                "operation": self.operation_name,
                "min": min(values),
                "max": max(values),
            },
        )


class AverageMetric(AggregateMetric):
    """
    Average aggregation: Aggregate<Avg, TargetMetric>

    Computes the mean of a target span-level metric for a session.
    Example: Average(ResponseCompleteness) over all AgentCalls.

    Convenience specialisation of AggregateMetric with the avg operation.
    """

    def __init__(self, target_metric_id: str, ontology_class: str = "Session"):
        super().__init__(
            target_metric_id=target_metric_id,
            operation_name="avg",
            operation_fn=statistics.mean,
            ontology_class=ontology_class,
        )
