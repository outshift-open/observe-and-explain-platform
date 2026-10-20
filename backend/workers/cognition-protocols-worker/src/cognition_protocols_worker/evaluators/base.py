"""What a protocol evaluator is.

An evaluator computes a protocol's metrics for one session. The worker runs it only when
the protocol's detector found the protocol activated in that session, and attaches what it
returns to the session's execution report for the protocol.

Metrics are MCE ``MetricResult`` objects, so an evaluator is usually a set of MCE metric
plugins (see ``McEvaluator``), but anything that returns results of that shape will do.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evaluation:
    #: the metrics that were computed
    passed: list[Any] = field(default_factory=list)
    #: the ones that did not apply to this session or failed (logged, never stored)
    failed: list[Any] = field(default_factory=list)


class ProtocolEvaluator(ABC):
    """Computes one Cognition protocol's metrics for a session.

    Subclass it, give it a ``name`` (the protocol's name, the same as its detector's) and
    implement ``evaluate``. Register an instance with ``EvaluatorRegistry.register`` or, from
    another package, as an entry point in the ``cognition_protocol_evaluators`` group.
    """

    #: the protocol's name, lower case, for example "accord"
    name: str = ""

    @abstractmethod
    def evaluate(self, session_id: str) -> Evaluation:
        """Compute the protocol's metrics for the session."""
