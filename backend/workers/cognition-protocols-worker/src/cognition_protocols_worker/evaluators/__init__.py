"""Modular evaluation of Cognition protocols: one evaluator per protocol that has metrics."""

from .base import Evaluation, ProtocolEvaluator
from .mce import McEvaluator
from .registry import ENTRY_POINT_GROUP, EvaluatorRegistry, builtin_evaluators, default_registry

__all__ = [
    "ENTRY_POINT_GROUP",
    "Evaluation",
    "EvaluatorRegistry",
    "McEvaluator",
    "ProtocolEvaluator",
    "builtin_evaluators",
    "default_registry",
]
