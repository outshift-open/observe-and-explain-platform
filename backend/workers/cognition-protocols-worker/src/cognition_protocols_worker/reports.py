"""What the workers record about Cognition protocols, written through the platform's Cognition protocol report provider."""

from __future__ import annotations

import logging
from typing import Any

from .detectors import ProtocolFinding

logger = logging.getLogger(__name__)


def record_findings(writer: Any, session_id: str, findings: dict[str, ProtocolFinding]) -> bool:
    """Store a session's ``CognitionProtocolReport`` and, for each *activated* protocol, who had it and who used it.

    The ``CognitionProtocolReport`` lists the protocols that were enabled and those that were activated. A protocol
    that was only enabled gets no ``CognitionProtocolExecutionReport``: there was no execution to report on.
    The ``CognitionProtocolReport`` is written even when no protocol was enabled or activated (two empty lists): it
    records that the session was checked.

    ``writer`` is an ``OXPCognitionProtocolReportProvider``. False if the session is not in the graph.
    """
    enabled = [name for name, f in findings.items() if f.enabled]
    activated = [name for name, f in findings.items() if f.activated]
    if not writer.save_cognition_protocol_report(session_id, enabled, activated):
        return False
    for name in activated:
        f = findings[name]
        writer.save_protocol_execution_report(
            session_id,
            name,
            enabled_evidence=f.enabled_evidence,
            skills_enabled=f.skills_enabled,
            skills_activated=f.skills_activated,
            agents_enabled=f.agents_enabled,
            agents_activated=f.agents_activated,
        )
    return True
