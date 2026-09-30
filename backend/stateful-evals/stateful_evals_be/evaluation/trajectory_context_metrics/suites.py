#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Named metric-suite selection with a stable legacy default."""

from __future__ import annotations

from typing import Literal

from .base import TrajectoryContextMetric
from .judge import MetricJudge
from .metrics import build_default_metrics, evaluate_high_level_metrics_batched
from .trajectory_metrics import (
    build_current_trajectory_metrics,
    build_legacy_trajectory_metrics,
)

LEGACY_METRIC_SUITE = "legacy_v1"
PAPER_METRIC_SUITE = "paper_v1"
PAPER_V2_METRIC_SUITE = "paper_v2"
MetricSuiteName = Literal["legacy_v1", "paper_v1", "paper_v2"]
SUPPORTED_METRIC_SUITES: tuple[MetricSuiteName, ...] = (
    LEGACY_METRIC_SUITE,
    PAPER_METRIC_SUITE,
    PAPER_V2_METRIC_SUITE,
)

PAPER_OUTCOME_METRICS = frozenset(
    {
        "Groundedness",
        "Task Completion",
        "Constraint Satisfaction",
    }
)


def build_metric_suite(
    metric_suite: MetricSuiteName | str = LEGACY_METRIC_SUITE,
    *,
    judge: MetricJudge | None = None,
) -> tuple[TrajectoryContextMetric, ...]:
    """Build one named suite without changing legacy defaults."""
    if metric_suite == LEGACY_METRIC_SUITE:
        return build_default_metrics(judge=judge)
    if metric_suite == PAPER_METRIC_SUITE:
        return build_legacy_trajectory_metrics(judge=judge)
    if metric_suite == PAPER_V2_METRIC_SUITE:
        return build_current_trajectory_metrics(judge=judge)
    supported = ", ".join(SUPPORTED_METRIC_SUITES)
    raise ValueError(
        f"Unknown trajectory-context metric suite {metric_suite!r}; "
        f"expected one of: {supported}"
    )


def evaluate_metric_suite_batched(
    context,
    *,
    metric_suite: MetricSuiteName | str = LEGACY_METRIC_SUITE,
    stateful_result=None,
    metrics: tuple[TrajectoryContextMetric, ...] | None = None,
    judge: MetricJudge | None = None,
    supplemental_context=None,
):
    """Evaluate a named suite and tag every result with its suite identity."""
    selected_metrics = metrics or build_metric_suite(metric_suite, judge=judge)
    results = evaluate_high_level_metrics_batched(
        context,
        stateful_result=stateful_result,
        metrics=selected_metrics,
        judge=judge,
        supplemental_context=supplemental_context,
    )
    for result in results:
        result.metadata["metric_suite"] = metric_suite
    return results
