"""CONCORD is built in: detected from its ``l9-concord-*`` skills, evaluated only when activated."""

import json

from cognition_protocols_worker.detectors import detect
from cognition_protocols_worker.evaluators import McEvaluator, builtin_evaluators
from cognition_protocols_worker.worker import CognitionProtocolsWorker
from worker_base.queue_message import BaseQueueMessage

from test_worker import FakeEvaluator, FakeReader, FakeWriter

LISTING = (
    "## Skills\n"
    "- **l9-concord-initiator**: run the CONCORD negotiation before delegating.\n"
    "- **l9-concord-receiver**: answer a CONCORD request.\n"
)
AGENTS = [{"spanId": "a1", "agentName": "sre"}, {"spanId": "a2", "agentName": "db"}]


def llm(agent_span, text=LISTING):
    return {"parentSpanId": agent_span, "prompt": json.dumps([{"role": "system", "content": text}])}


def script(agent_span, skill="l9-concord-initiator", args=("init", "--agents", "sre,db")):
    return {
        "parentSpanId": agent_span,
        "toolName": "run_skill_script",
        "toolArguments": json.dumps({"skill": skill, "script": "concordv2.py", "args": list(args)}),
    }


def test_concord_listed_in_a_system_prompt_is_enabled_but_not_activated():
    found = detect({"agent_spans": AGENTS, "llm_spans": [llm("a1")], "tool_spans": []})["concord"]
    assert found.enabled and not found.activated and found.enabled_evidence == "system_prompt"
    assert found.enabled_by_agent == {"sre": ["l9-concord-initiator", "l9-concord-receiver"]}
    assert found.agents_enabled == ["sre"]


def test_running_the_initiator_script_activates_concord_for_that_agent():
    ctx = {"agent_spans": AGENTS, "llm_spans": [llm("a1")], "tool_spans": [script("a1")]}
    found = detect(ctx)["concord"]
    assert found.enabled and found.activated
    assert found.activated_by_agent == {"sre": ["l9-concord-initiator"]}


def test_a_specialist_activating_the_receiver_is_recorded_with_its_agent():
    activate = {"parentSpanId": "a2", "toolName": "activate_skill", "toolArguments": json.dumps({"name": "l9-concord-receiver"})}
    found = detect({"agent_spans": AGENTS, "llm_spans": [], "tool_spans": [script("a1"), activate]})["concord"]
    assert found.activated_by_agent == {"sre": ["l9-concord-initiator"], "db": ["l9-concord-receiver"]}
    assert found.enabled_evidence == "activation"  # no readable prompt lists it, but it was called


def test_concord_and_accord_do_not_leak_into_each_other():
    accord = {"parentSpanId": "a1", "toolName": "activate_skill", "toolArguments": json.dumps({"name": "l9-accord-initiator"})}
    findings = detect({"agent_spans": AGENTS, "llm_spans": [], "tool_spans": [accord]})
    assert findings["accord"].activated and not findings["concord"].enabled
    findings = detect({"agent_spans": AGENTS, "llm_spans": [], "tool_spans": [script("a1")]})
    assert findings["concord"].activated and not findings["accord"].enabled


def test_the_built_in_concord_evaluator_uses_the_concord_config():
    evaluator = {e.name: e for e in builtin_evaluators()}["concord"]
    assert isinstance(evaluator, McEvaluator) and evaluator.config_path.name == "concord_mce_config.yaml"
    assert evaluator.config_path.is_file()


async def run(spans, evaluators):
    writer = FakeWriter()
    worker = CognitionProtocolsWorker(rabbitmq_url="amqp://x", input_queue="q", reader=FakeReader(spans), writer=writer, evaluators=evaluators)
    return await worker.handle_message(BaseQueueMessage(session_id="sess")), writer


async def test_an_activated_concord_session_has_its_metrics_computed_and_stored():
    concord, accord = FakeEvaluator("concord", passed=["C1"]), FakeEvaluator("accord")
    result, writer = await run({"agent_spans": AGENTS, "llm_spans": [llm("a1")], "tool_spans": [script("a1")]}, [accord, concord])
    assert result is True
    assert writer.cognition_protocol_reports == [("sess", ["concord"], ["concord"])]
    assert [p for _, p, _ in writer.participation] == ["concord"]
    assert writer.metrics == [("sess", "concord", ["C1"])]
    assert accord.calls == []  # ACCORD was not activated, so it is not evaluated


async def test_concord_only_enabled_is_recorded_but_not_evaluated():
    concord = FakeEvaluator("concord")
    result, writer = await run({"agent_spans": AGENTS, "llm_spans": [llm("a1")], "tool_spans": []}, [concord])
    assert result is True and writer.cognition_protocol_reports == [("sess", ["concord"], [])]
    assert concord.calls == [] and writer.participation == []
