"""ACCORD: skills named ``l9-accord-*``, and the ACCORD MCE metrics (``ioc-accord-mce-metrics``)."""

from __future__ import annotations

from importlib import resources

from cognition_protocols_worker.detectors.skills import SkillProtocolDetector
from cognition_protocols_worker.evaluators.mce import McEvaluator

NAME = "accord"
SKILL_PREFIX = "l9-accord-"
CONFIG_RESOURCE = "accord_mce_config.yaml"


def detector() -> SkillProtocolDetector:
    return SkillProtocolDetector(NAME, SKILL_PREFIX)


def evaluator() -> McEvaluator:
    return McEvaluator(NAME, resources.files(__package__) / CONFIG_RESOURCE)
