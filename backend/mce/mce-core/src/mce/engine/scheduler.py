#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from mce.core.metric import Metric
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class TopologicalScheduler:
    """
    Resolves metric execution order using Kahn's Algorithm for DAGs.
    Returns generations of independent metric IDs that can run in parallel.
    """

    def schedule(self, metrics: list[Metric]) -> list[list[str]]:
        # dict.fromkeys preserves insertion order and de-duplicates — deterministic across restarts.
        nodes = dict.fromkeys(m.metric_id for m in metrics)
        adj = defaultdict(list)
        in_degree = {mid: 0 for mid in nodes}

        # Build Graph
        # Dependency flow: Metric depends on Dependency
        # Execution flow: Dependency -> Metric
        # Edge direction in graph: Dependency -> Metric
        for metric in metrics:
            for dep_id in metric.dependencies:
                if dep_id in nodes:
                    adj[dep_id].append(metric.metric_id)
                    in_degree[metric.metric_id] += 1
                else:
                    logger.debug(
                        f"Metric {metric.metric_id} depends on excluded {dep_id}"
                    )

        # Initial Queue (Generation 0): Nodes with no dependencies
        queue = [mid for mid in nodes if in_degree[mid] == 0]
        generations = []
        processed_count = 0

        while queue:
            generations.append(queue)
            processed_count += len(queue)

            next_queue = []
            for u in queue:
                for v in adj[u]:
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        next_queue.append(v)
            queue = next_queue

        if processed_count != len(nodes):
            raise ValueError(
                f"Cycle detected in metric dependencies "
                f"({len(nodes) - processed_count} metric(s) unreachable). "
                f"Check dependency declarations."
            )

        return generations
