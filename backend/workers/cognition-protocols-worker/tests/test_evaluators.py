"""Evaluators are pluggable like detectors, and the MCE-backed one runs a service on a metrics config."""

from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from cognition_protocols_worker import plugins
from cognition_protocols_worker.evaluators import (
    Evaluation,
    EvaluatorRegistry,
    McEvaluator,
    ProtocolEvaluator,
    builtin_evaluators,
)
from cognition_protocols_worker.evaluators import registry as registry_module


class Tooly(ProtocolEvaluator):
    name = "tooly"

    def evaluate(self, session_id):
        return Evaluation(passed=[session_id])


TOOLY_INSTANCE = Tooly()


def factory():
    class Made(Tooly):
        name = "made"

    return Made()


def test_accord_and_concord_are_built_in():
    assert [e.name for e in builtin_evaluators()] == ["accord", "concord"]


def test_registry_rejects_a_second_evaluator_for_the_same_protocol():
    registry = EvaluatorRegistry(builtin_evaluators())
    with pytest.raises(ValueError):
        registry.register(McEvaluator("accord", "x.yaml"))
    registry.register(McEvaluator("accord", "x.yaml"), replace=True)
    with pytest.raises(TypeError):
        registry.register(object())


def _entry(name, value):
    return EntryPoint(name=name, value=value, group=registry_module.ENTRY_POINT_GROUP)


def test_installed_packages_add_evaluators_through_entry_points(monkeypatch):
    entries = [_entry("a", f"{__name__}:Tooly"), _entry("b", f"{__name__}:factory"), _entry("c", "no_such_module:Nope")]
    monkeypatch.setattr(plugins, "entry_points", lambda group: [e for e in entries if e.group == group])
    registry = EvaluatorRegistry(builtin_evaluators())
    registry.load_entry_points()  # the broken one is skipped
    assert registry.names() == ["accord", "concord", "made", "tooly"]


def test_mce_evaluator_runs_the_services_session_computation_with_the_protocols_config():
    calls = []

    class Service:
        def _compute_session_results(self, session_id):
            calls.append(session_id)
            return ["ok"], ["skipped"]

    built = []
    evaluator = McEvaluator("p", "p.yaml", service_factory=lambda: built.append(1) or Service())
    first = evaluator.evaluate("s1")
    evaluator.evaluate("s2")
    assert (first.passed, first.failed) == (["ok"], ["skipped"])
    assert calls == ["s1", "s2"] and built == [1]  # the service is built once


@pytest.mark.parametrize("protocol", ["accord", "concord"])
def test_the_protocol_config_names_only_installed_plugins_and_keeps_mce_cache_off(protocol):
    import yaml
    from mce.core.registry.discovery import _discover_plugin_metrics

    config = Path(registry_module.__file__).parents[1] / "protocols" / f"{protocol}_mce_config.yaml"
    cfg = yaml.safe_load(config.read_text())
    plugins_installed = {m.metric_id for m in _discover_plugin_metrics()}
    assert cfg["metrics"]["Session"] and set(cfg["metrics"]["Session"]) <= plugins_installed
    assert cfg["cache"] == {"read": False, "write": False}  # nothing lands on the Session
