import json
from pathlib import Path

from cognition_protocols_worker.detectors import detect
from cognition_protocols_worker.reports import record_findings

SYSTEM = (
    "You are an SRE agent.\n\n## Skills\n"
    "- **severity-classification**: SEV classification criteria.\n"
    "- **l9-accord-initiator**: MANDATORY pre-delegation coordination protocol.\n"
)


def llm(agent_span, system):
    return {"parentSpanId": agent_span, "prompt": json.dumps([{"role": "system", "content": system}, {"role": "user", "content": "go"}])}


def tool(agent_span, name, args):
    return {"parentSpanId": agent_span, "toolName": name, "toolArguments": args}


AGENTS = [{"spanId": "a1", "agentName": "sre"}, {"spanId": "a2", "agentName": "db"}]


def test_enabled_and_triggered():
    ctx = {
        "agent_spans": AGENTS,
        "llm_spans": [llm("a1", SYSTEM), llm("a2", "- **data-access-protocol**: x")],
        "tool_spans": [tool("a1", "activate_skill", json.dumps({"name": "l9-accord-initiator"}))],
    }
    found = detect(ctx)["accord"]
    assert found.enabled and found.activated and found.enabled_evidence == "system_prompt"
    assert found.enabled_by_agent == {"sre": ["l9-accord-initiator"]}
    assert found.activated_by_agent == {"sre": ["l9-accord-initiator"]}


def test_enabled_but_never_triggered():
    found = detect({"agent_spans": AGENTS, "llm_spans": [llm("a1", SYSTEM)], "tool_spans": [tool("a1", "get_logs", "{}")]})["accord"]
    assert found.enabled and not found.activated


def test_neither_enabled_nor_triggered():
    found = detect({"agent_spans": AGENTS, "llm_spans": [llm("a1", "- **data-access-protocol**: x")], "tool_spans": []})["accord"]
    assert not found.enabled and not found.activated


def test_a_skill_that_is_only_mentioned_is_not_enabled():
    prose = "Remember the l9-accord-initiator skill exists.\nUse **l9-accord-initiator** sometimes."
    assert not detect({"agent_spans": AGENTS, "llm_spans": [llm("a1", prose)], "tool_spans": []})["accord"].enabled


def test_triggered_without_a_readable_listing_still_counts_as_enabled():
    ctx = {"agent_spans": AGENTS, "llm_spans": [], "tool_spans": [tool("a1", "run_skill_script", '{"args": ["verify", "--x", "[\\"cut off')]}
    ctx["tool_spans"][0]["toolArguments"] = '{"skill": "l9-accord-initiator", "script": "a.py", "args": ["verify", "--required'
    found = detect(ctx)["accord"]
    assert found.activated and found.enabled and found.enabled_evidence == "activation"


def test_another_agents_skill_name_in_arguments_is_ignored():
    ctx = {"agent_spans": AGENTS, "llm_spans": [], "tool_spans": [tool("a1", "activate_skill", json.dumps({"name": "triage-protocol"}))]}
    assert not detect(ctx)["accord"].activated


class FakeWriter:
    """Stands in for the platform's OXPCognitionProtocolReportProvider and records what it is asked to store."""

    def __init__(self, session_exists=True):
        self.session_exists = session_exists
        self.cognition_protocol_reports, self.participation = [], []

    def save_cognition_protocol_report(self, session_id, protocols_enabled, protocols_activated):
        self.cognition_protocol_reports.append((session_id, list(protocols_enabled), list(protocols_activated)))
        return self.session_exists

    def save_protocol_execution_report(self, session_id, protocol, **fields):
        self.participation.append((session_id, protocol, fields))
        return True


def test_the_cognition_protocol_report_gets_the_protocols_enabled_and_activated():
    findings = detect({"agent_spans": AGENTS, "llm_spans": [llm("a1", SYSTEM)], "tool_spans": []})
    writer = FakeWriter()
    assert record_findings(writer, "sess", findings)
    assert writer.cognition_protocol_reports == [("sess", ["accord"], [])]


def test_each_activated_protocol_gets_its_participation_recorded():
    findings = detect(
        {
            "agent_spans": AGENTS,
            "llm_spans": [llm("a1", SYSTEM)],
            "tool_spans": [tool("a1", "activate_skill", json.dumps({"name": "l9-accord-initiator"}))],
        }
    )
    writer = FakeWriter()
    record_findings(writer, "sess", findings)
    ((session_id, protocol, fields),) = writer.participation
    assert (session_id, protocol) == ("sess", "accord")
    assert fields["agents_enabled"] == ["sre"] and fields["agents_activated"] == ["sre"]
    assert fields["skills_activated"] == ["l9-accord-initiator"] and fields["enabled_evidence"] == "system_prompt"


def test_a_new_skill_protocol_is_one_more_detector():
    from cognition_protocols_worker.detectors import SkillProtocolDetector, builtin_detectors

    ctx = {"agent_spans": AGENTS, "llm_spans": [llm("a1", SYSTEM + "- **l9-other-x**: y\n")], "tool_spans": [tool("a2", "activate_skill", '{"name": "l9-other-x"}')]}
    findings = detect(ctx, [*builtin_detectors(), SkillProtocolDetector("other", "l9-other-")])
    assert findings["other"].enabled and findings["other"].activated and findings["other"].agents_activated == ["db"]
    assert findings["accord"].enabled and not findings["accord"].activated  # protocols do not leak into each other
    writer = FakeWriter()
    record_findings(writer, "sess", findings)
    assert writer.cognition_protocol_reports == [("sess", ["accord", "other"], ["other"])]
    assert [p for _, p, _ in writer.participation] == ["other"]  # accord was only enabled, so it has no execution report


def test_a_skill_protocol_can_have_several_prefixes():
    from cognition_protocols_worker.detectors import SkillProtocolDetector

    det = SkillProtocolDetector("multi", "l9-a-", "l9-b-")
    ctx = {"agent_spans": AGENTS, "llm_spans": [llm("a1", "- **l9-a-one**: x\n- **l9-b-two**: y\n")], "tool_spans": []}
    assert det.detect(ctx).skills_enabled == ["l9-a-one", "l9-b-two"]


def test_a_protocol_that_was_only_enabled_gets_no_execution_report_but_is_listed():
    writer = FakeWriter()
    record_findings(writer, "sess", detect({"agent_spans": AGENTS, "llm_spans": [llm("a1", SYSTEM)], "tool_spans": []}))
    assert writer.cognition_protocol_reports == [("sess", ["accord"], [])]  # the CognitionProtocolReport still says it was enabled
    assert writer.participation == []  # there was no execution to report on


def test_no_protocol_enabled_or_activated_still_gives_an_empty_cognition_protocol_report():
    writer = FakeWriter()
    assert record_findings(writer, "sess", detect({"agent_spans": AGENTS, "llm_spans": [], "tool_spans": []}))
    assert writer.cognition_protocol_reports == [("sess", [], [])] and writer.participation == []


def test_a_protocol_that_was_not_enabled_gets_no_execution_report():
    writer = FakeWriter()
    record_findings(writer, "sess", detect({"agent_spans": AGENTS, "llm_spans": [], "tool_spans": []}))
    assert writer.participation == []


def test_nothing_more_is_written_for_a_session_that_is_not_in_the_graph():
    writer = FakeWriter(session_exists=False)
    findings = detect({"agent_spans": AGENTS, "llm_spans": [llm("a1", SYSTEM)], "tool_spans": []})
    assert not record_findings(writer, "ghost", findings)
    assert writer.participation == []


def test_no_worker_code_holds_a_cypher_query():
    """The graph is reached only through the platform's providers."""
    sources = [p for pkg in Path(__file__).resolve().parents[2].glob("*/src") for p in pkg.rglob("*.py")]
    assert sources
    for path in sources:
        text = path.read_text()
        for marker in ("MERGE (", "MATCH (", "DETACH DELETE", "execute_command", ".execute("):
            assert marker not in text, f"{path.name} reaches the graph directly: {marker!r}"
