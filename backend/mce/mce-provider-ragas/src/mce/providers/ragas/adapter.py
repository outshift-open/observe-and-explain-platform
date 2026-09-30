#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any, Dict
from mce.core.metric import MetricScope
from ..base_wrapper import ExternalMetricWrapper


class RagasMetricWrapper(ExternalMetricWrapper):
    def __init__(self, metric_name: str, requirements: Dict, mode: str = "precision"):
        name_with_mode = f"{metric_name}_{mode}" if mode != "precision" else metric_name
        super().__init__(
            name_with_mode, {"requirements": requirements}, "Ragas", MetricScope.SESSION
        )
        self._mode = mode
        self._raw_metric_name = metric_name

    def _check_availability(self):
        import importlib.util

        if importlib.util.find_spec("ragas") is None:
            self._availability_status = False
            self._availability_error = "ragas package not found"

    def call_external_sync(self, **kwargs) -> Any:
        raise NotImplementedError(
            f"RagasMetricWrapper '{self._raw_metric_name}' has no real implementation. "
            "Provide a concrete subclass that calls ragas.evaluate()."
        )


def create_wrapper(metric_name: str) -> RagasMetricWrapper:
    # Handle composite names like "TopicAdherenceScore.f1"
    mode = "precision"
    real_name = metric_name
    if "." in metric_name and metric_name.startswith("ragas."):
        parts = metric_name.split(".")
        if len(parts) == 3:
            real_name = parts[1]
            mode = parts[2]

    config = {
        "TopicAdherenceScore": {"required_input_parameters": ["conversation_elements"]},
    }

    # Check against real name
    if real_name in config:
        return RagasMetricWrapper(real_name, config[real_name], mode)

    raise ValueError(f"Unknown Ragas metric: {metric_name}")
