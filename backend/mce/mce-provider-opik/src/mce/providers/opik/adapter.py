#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any, Dict
from mce.core.metric import MetricScope
from ..base_wrapper import ExternalMetricWrapper
from .provider import OpikProvider


class OpikMetricWrapper(ExternalMetricWrapper):
    def __init__(self, metric_name: str, requirements: Dict):
        super().__init__(
            metric_name,
            {"requirements": requirements},
            "Opik",
            MetricScope.EXECUTION_ELEMENT,
        )
        self._provider = OpikProvider()

    def _check_availability(self):
        import importlib.util

        if importlib.util.find_spec("opik") is None:
            self._availability_status = False
            self._availability_error = "opik package not found"

    def init_with_model(self, model: Any) -> bool:
        self._model = model
        self._provider.set_model(model)
        return True

    def call_external_sync(self, **kwargs) -> Any:
        return self._provider.evaluate(self._metric_name, kwargs)


def create_wrapper(metric_name: str) -> OpikMetricWrapper:
    config = {
        "Hallucination": {
            "required_input_parameters": ["input_payload", "output_payload"]
        },
        "Sentiment": {"required_input_parameters": ["input_payload", "output_payload"]},
    }
    if metric_name in config:
        return OpikMetricWrapper(metric_name, config[metric_name])
    raise ValueError(f"Unknown Opik metric: {metric_name}")
