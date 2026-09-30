#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import importlib
from typing import Any

# Shared Opik provider that owns metric instances and conversions.


class OpikProvider:
    def __init__(self, model: Any = None):
        self._model = model
        self._instances: dict[str, Any] = {}

    def set_model(self, model: Any) -> None:
        self._model = model
        self._instances = {}

    def get_metric(self, metric_name: str) -> Any:
        if metric_name in self._instances:
            return self._instances[metric_name]

        try:
            module = importlib.import_module("opik.evaluation.metrics")
        except Exception:
            return None

        metric_cls = getattr(module, metric_name, None)
        if metric_cls is None:
            return None

        try:
            metric = metric_cls(model=self._model)
        except TypeError:
            metric = metric_cls()

        self._instances[metric_name] = metric
        return metric

    def evaluate(self, metric_name: str, context: dict[str, Any]) -> Any:
        metric = self.get_metric(metric_name)
        if metric is None:
            return 0.0

        args = {
            "input": context.get("input_text"),
            "output": context.get("output_text"),
            "context": context.get("context") or context.get("retrieval_context"),
        }
        if hasattr(metric, "score"):
            return metric.score(**{k: v for k, v in args.items() if v is not None})
        return 0.0
