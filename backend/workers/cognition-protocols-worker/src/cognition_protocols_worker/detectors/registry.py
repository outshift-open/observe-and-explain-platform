"""The protocols the worker looks for, and how another package adds one.

ACCORD and CONCORD are built in. Any installed package can add a protocol by declaring an entry point in
the ``cognition_protocol_detectors`` group, in its ``pyproject.toml``::

    [project.entry-points.cognition_protocol_detectors]
    mine = "my_package.detectors:MyDetector"

The entry point names a ``ProtocolDetector`` subclass, an instance of one, or a function
that returns one. Nothing in this package needs to change.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from cognition_protocols_worker import plugins

from .base import ProtocolDetector, ProtocolFinding

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "cognition_protocol_detectors"


class DetectorRegistry(plugins.Registry[ProtocolDetector]):
    base = ProtocolDetector
    group = ENTRY_POINT_GROUP

    def detectors(self) -> list[ProtocolDetector]:
        return self.items()


def builtin_detectors() -> list[ProtocolDetector]:
    """The protocols known out of the box."""
    from cognition_protocols_worker.protocols import accord, concord

    return [accord.detector(), concord.detector()]


_default: DetectorRegistry | None = None


def default_registry() -> DetectorRegistry:
    """The built-in protocols plus the installed packages' entry points, built once."""
    global _default
    if _default is None:
        registry = DetectorRegistry(builtin_detectors())
        registry.load_entry_points()
        _default = registry
    return _default


def detect(context: dict[str, Any], detectors: Iterable[ProtocolDetector] | None = None) -> dict[str, ProtocolFinding]:
    """Run each detector on a session's spans: findings by protocol name.

    A detector that fails is logged and left out; the others still report.
    """
    findings: dict[str, ProtocolFinding] = {}
    for detector in detectors if detectors is not None else default_registry().detectors():
        try:
            finding = detector.detect(context)
        except Exception:
            logger.exception("Cognition protocol detector %r failed; its protocol is not reported", detector.name)
            continue
        finding.protocol = finding.protocol or detector.name
        findings[detector.name] = finding
    return findings
