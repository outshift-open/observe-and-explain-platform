#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
DeepEval Metrics Factory
========================
Centralized metric instantiation logic for DeepEval provider.
Simplifies provider.py by extracting metric creation logic.
"""

from __future__ import annotations

from typing import Callable


def get_metric_factory() -> dict[str, Callable]:
    """
    Returns a dictionary mapping metric names to factory functions.

    Each factory function takes (model_instance) and returns a configured metric.
    Lazy imports ensure DeepEval dependencies are only loaded when metrics are created.

    Returns:
        Dict mapping metric name to factory function
    """
    from . import wrapper_config

    def create_answer_relevancy(model):
        from deepeval.metrics import AnswerRelevancyMetric

        return AnswerRelevancyMetric(model=model)

    def create_role_adherence(model):
        from deepeval.metrics import RoleAdherenceMetric

        return RoleAdherenceMetric(model=model, verbose_mode=False)

    def create_task_completion(model):
        from deepeval.metrics import TaskCompletionMetric

        return TaskCompletionMetric(model=model, verbose_mode=False)

    def create_conversation_completeness(model):
        from deepeval.metrics import ConversationCompletenessMetric

        return ConversationCompletenessMetric(model=model, verbose_mode=False)

    def create_bias(model):
        from deepeval.metrics import BiasMetric

        return BiasMetric(model=model)

    def create_toxicity(model):
        from deepeval.metrics import ToxicityMetric

        return ToxicityMetric(model=model)

    def create_coherence(model):
        from deepeval.metrics import GEval

        return GEval(
            name="Coherence",
            criteria=wrapper_config.COHERENCE_CRITERIA,
            evaluation_params=wrapper_config.COHERENCE_EVAL_PARAMS,
            model=model,
        )

    def create_groundedness(model):
        from deepeval.metrics import GEval

        return GEval(
            name="Groundedness",
            evaluation_steps=wrapper_config.EVALUATION_STEPS_GROUNDEDNESS,
            evaluation_params=wrapper_config.GROUNDEDNESS_EVAL_PARAMS,
            model=model,
        )

    def create_tonality(model):
        from deepeval.metrics import GEval

        return GEval(
            name="Tonality",
            evaluation_steps=wrapper_config.EVALUATION_STEPS_TONALITY,
            evaluation_params=wrapper_config.TONALITY_EVAL_PARAMS,
            model=model,
        )

    def create_answer_correctness(model):
        from deepeval.metrics import GEval

        return GEval(
            name="AnswerCorrectness",
            criteria=wrapper_config.CRITERIA_CORRECTNESS,
            evaluation_params=wrapper_config.CORRECTNESS_EVAL_PARAMS,
            model=model,
        )

    def create_general_structure(model):
        from deepeval.metrics import GEval

        return GEval(
            name="GeneralStructureAndStyle",
            criteria=wrapper_config.CRITERIA_GENERAL_STRUCTURE,
            evaluation_params=wrapper_config.GENERAL_STRUCTURE_EVAL_PARAMS,
            model=model,
        )

    # Registry mapping metric names (with aliases) to factory functions
    registry = {}

    # AnswerRelevancy
    for name in ["AnswerRelevancy", "AnswerRelevancyMetric"]:
        registry[name] = create_answer_relevancy

    # RoleAdherence
    for name in ["RoleAdherence", "RoleAdherenceMetric"]:
        registry[name] = create_role_adherence

    # TaskCompletion
    for name in ["TaskCompletion", "TaskCompletionMetric"]:
        registry[name] = create_task_completion

    # ConversationCompleteness
    for name in ["ConversationCompleteness", "ConversationCompletenessMetric"]:
        registry[name] = create_conversation_completeness

    # Bias
    for name in ["Bias", "BiasMetric"]:
        registry[name] = create_bias

    # Toxicity
    for name in ["Toxicity", "ToxicityMetric"]:
        registry[name] = create_toxicity

    # Coherence (GEval)
    for name in ["Coherence", "CoherenceMetric"]:
        registry[name] = create_coherence

    # Groundedness (GEval)
    for name in ["Groundedness", "GroundednessMetric"]:
        registry[name] = create_groundedness

    # Tonality (GEval)
    for name in ["Tonality", "TonalityMetric"]:
        registry[name] = create_tonality

    # AnswerCorrectness (GEval)
    for name in ["AnswerCorrectness", "AnswerCorrectnessMetric"]:
        registry[name] = create_answer_correctness

    # GeneralStructureAndStyle (GEval)
    for name in ["GeneralStructureAndStyle", "GeneralStructureAndStyleMetric"]:
        registry[name] = create_general_structure

    return registry
