#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from .wrapper import DeepEvalMetricWrapper


def get_available_metrics() -> list[type[DeepEvalMetricWrapper]]:
    # In V2, we might simply return a list of factories or registered names
    # For now, let's expose specific predefined wrappers
    return []


def create_wrapper(metric_name: str) -> DeepEvalMetricWrapper:
    # Replicate logic from build_metric_configurations
    config = {
        "AnswerRelevancyMetric": {
            "requirements": {
                "entity_type": ["llm"],
                "aggregation_level": "span",
                "required_input_parameters": ["input_query", "final_response"],
            }
        },
        "RoleAdherenceMetric": {
            "requirements": {
                "entity_type": ["llm", "tool"],
                "aggregation_level": "session",
                "required_input_parameters": ["conversation_elements"],
            }
        },
        # ... Add others
    }

    if metric_name in config:
        return DeepEvalMetricWrapper(metric_name, config[metric_name])
    raise ValueError(f"Unknown DeepEval metric: {metric_name}")
