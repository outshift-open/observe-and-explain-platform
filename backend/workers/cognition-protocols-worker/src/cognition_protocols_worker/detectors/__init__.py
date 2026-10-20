"""Modular detection of Cognition protocols in a session's spans."""

from .base import ProtocolDetector, ProtocolFinding, SessionSpans
from .registry import ENTRY_POINT_GROUP, DetectorRegistry, builtin_detectors, default_registry, detect
from .skills import SkillProtocolDetector

__all__ = [
    "ENTRY_POINT_GROUP",
    "DetectorRegistry",
    "ProtocolDetector",
    "ProtocolFinding",
    "SessionSpans",
    "SkillProtocolDetector",
    "builtin_detectors",
    "default_registry",
    "detect",
]
