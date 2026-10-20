"""The protocols that have metrics, and how another package adds one.

ACCORD and CONCORD are built in. Any installed package can add a protocol's evaluator by declaring an entry
point in the ``cognition_protocol_evaluators`` group::

    [project.entry-points.cognition_protocol_evaluators]
    mine = "my_package.evaluator:MyEvaluator"

A protocol need not have an evaluator (it is then only detected), and an evaluator is only
run for a session where the protocol with the same name was found activated.
"""

from __future__ import annotations

from cognition_protocols_worker import plugins

from .base import ProtocolEvaluator

ENTRY_POINT_GROUP = "cognition_protocol_evaluators"


class EvaluatorRegistry(plugins.Registry[ProtocolEvaluator]):
    base = ProtocolEvaluator
    group = ENTRY_POINT_GROUP

    def evaluators(self) -> list[ProtocolEvaluator]:
        return self.items()


def builtin_evaluators() -> list[ProtocolEvaluator]:
    """The protocols with metrics out of the box."""
    from cognition_protocols_worker.protocols import accord, concord

    return [accord.evaluator(), concord.evaluator()]


_default: EvaluatorRegistry | None = None


def default_registry() -> EvaluatorRegistry:
    """The built-in evaluators plus the installed packages' entry points, built once."""
    global _default
    if _default is None:
        registry = EvaluatorRegistry(builtin_evaluators())
        registry.load_entry_points()
        _default = registry
    return _default
