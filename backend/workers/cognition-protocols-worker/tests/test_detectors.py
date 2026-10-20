"""The detectors are pluggable: a protocol is one ProtocolDetector, found in a registry or an entry point."""

import json
from importlib.metadata import EntryPoint

import pytest
from cognition_protocols_worker.detectors import (
    DetectorRegistry,
    ProtocolDetector,
    ProtocolFinding,
    SessionSpans,
    SkillProtocolDetector,
    builtin_detectors,
    detect,
)
from cognition_protocols_worker import plugins
from cognition_protocols_worker.detectors import registry as registry_module

AGENTS = [{"spanId": "a1", "agentName": "sre"}, {"spanId": "a2", "agentName": "db"}]


class ToolProtocol(ProtocolDetector):
    """A protocol that is not skill based: it is "used" when an agent calls its tool."""

    name = "tooly"

    def detect(self, context):
        spans = SessionSpans.of(context)
        found = ProtocolFinding(self.name)
        for span in spans.tools:
            if span.get("toolName") == "tooly_handshake":
                found.activated_by_agent.setdefault(spans.agent_of(span), []).append("tooly_handshake")
        found.activated = bool(found.activated_by_agent)
        found.enabled, found.enabled_evidence = found.activated, "activation"
        return found


class Broken(ProtocolDetector):
    name = "broken"

    def detect(self, context):
        raise RuntimeError("boom")


CTX = {"agent_spans": AGENTS, "llm_spans": [], "tool_spans": [{"parentSpanId": "a2", "toolName": "tooly_handshake", "toolArguments": "{}"}]}


def test_accord_and_concord_are_built_in():
    assert [d.name for d in builtin_detectors()] == ["accord", "concord"]


def test_a_detector_that_is_not_skill_based_plugs_in():
    findings = detect(CTX, [*builtin_detectors(), ToolProtocol()])
    assert findings["tooly"].activated and findings["tooly"].agents_activated == ["db"]
    assert not findings["accord"].enabled


def test_registry_rejects_a_second_detector_for_the_same_protocol():
    registry = DetectorRegistry(builtin_detectors())
    with pytest.raises(ValueError):
        registry.register(SkillProtocolDetector("accord", "x-"))
    registry.register(SkillProtocolDetector("accord", "x-"), replace=True)  # unless asked to
    with pytest.raises(TypeError):
        registry.register(object())


def test_a_failing_detector_does_not_take_the_others_down():
    findings = detect(CTX, [Broken(), ToolProtocol()])
    assert "broken" not in findings and findings["tooly"].activated


def _entry_points(monkeypatch, *entries):
    monkeypatch.setattr(plugins, "entry_points", lambda group: [e for e in entries if e.group == group])


def _entry(name, value):
    return EntryPoint(name=name, value=value, group=registry_module.ENTRY_POINT_GROUP)


def test_installed_packages_add_detectors_through_entry_points(monkeypatch):
    # an instance, a subclass and a factory function are all accepted
    _entry_points(
        monkeypatch,
        _entry("tooly", f"{__name__}:ToolProtocol"),
        _entry("inst", f"{__name__}:INSTANCE"),
        _entry("fact", f"{__name__}:factory"),
    )
    registry = DetectorRegistry(builtin_detectors())
    registry.load_entry_points()
    assert registry.names() == ["accord", "concord", "factory-made", "instance-made", "tooly"]


def test_a_broken_or_clashing_entry_point_is_skipped_not_fatal(monkeypatch):
    _entry_points(
        monkeypatch,
        _entry("missing", "no_such_module_anywhere:Thing"),
        _entry("notadetector", f"{__name__}:NOT_A_DETECTOR"),
        _entry("clash", f"{__name__}:ACCORD_CLASH"),
        _entry("good", f"{__name__}:ToolProtocol"),
    )
    registry = DetectorRegistry(builtin_detectors())
    registry.load_entry_points()
    assert registry.names() == ["accord", "concord", "tooly"]
    assert registry.get("accord").prefixes == ("l9-accord-",)  # the clash did not replace the built-in


def test_the_skill_worker_default_is_every_registered_protocol(monkeypatch):
    registry = DetectorRegistry([*builtin_detectors(), ToolProtocol()])
    monkeypatch.setattr(registry_module, "_default", registry)
    assert set(detect(CTX)) == {"accord", "concord", "tooly"}


INSTANCE = SkillProtocolDetector("instance-made", "l9-inst-")
NOT_A_DETECTOR = 42
ACCORD_CLASH = SkillProtocolDetector("accord", "l9-clash-")


def factory():
    return SkillProtocolDetector("factory-made", "l9-fact-")
