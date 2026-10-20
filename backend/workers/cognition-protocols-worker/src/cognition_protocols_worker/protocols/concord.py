"""CONCORD: skills named ``l9-concord-*``, and the CONCORD MCE metrics (``ioc-concord-mce-metrics``).

Enabled and activated are read from the skills, as for ACCORD: ``l9-concord-initiator`` (the SRE's side) and
``l9-concord-receiver`` (the specialists'). The metrics themselves look for the initiator script's own calls, so
a session where only the receiver was activated is recorded as activated but every metric is skipped.
"""

from __future__ import annotations

from importlib import resources

from cognition_protocols_worker.detectors.skills import SkillProtocolDetector
from cognition_protocols_worker.evaluators.mce import McEvaluator

NAME = "concord"
SKILL_PREFIX = "l9-concord-"
CONFIG_RESOURCE = "concord_mce_config.yaml"


def detector() -> SkillProtocolDetector:
    return SkillProtocolDetector(NAME, SKILL_PREFIX)


def evaluator() -> McEvaluator:
    return McEvaluator(NAME, resources.files(__package__) / CONFIG_RESOURCE)
