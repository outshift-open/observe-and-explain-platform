"""The merged worker: detect protocols, then evaluate the ones that were activated."""

import json

from cognition_protocols_worker.detectors import ProtocolDetector, ProtocolFinding, builtin_detectors
from cognition_protocols_worker.evaluators import Evaluation, ProtocolEvaluator
from cognition_protocols_worker.worker import CognitionProtocolsWorker
from worker_base.queue_message import BaseQueueMessage

LISTING = "## Skills\n- **l9-accord-initiator**: MANDATORY protocol.\n"
ACTIVATED = {
    "agent_spans": [{"spanId": "a1", "agentName": "sre"}],
    "llm_spans": [{"parentSpanId": "a1", "prompt": json.dumps([{"role": "system", "content": LISTING}])}],
    "tool_spans": [{"parentSpanId": "a1", "toolName": "activate_skill", "toolArguments": json.dumps({"name": "l9-accord-initiator"})}],
}
ENABLED_ONLY = {**ACTIVATED, "tool_spans": []}
NOTHING = {"agent_spans": [{"spanId": "a1", "agentName": "sre"}], "llm_spans": [], "tool_spans": []}


class FakeReader:
    def __init__(self, spans):
        self.spans = spans

    def fetch(self, session_id, scope):
        return self.spans


class FakeWriter:
    def __init__(self, exists=True, metrics_ok=True):
        self.exists, self.metrics_ok = exists, metrics_ok
        self.cognition_protocol_reports, self.participation, self.metrics = [], [], []

    def save_cognition_protocol_report(self, session_id, protocols_enabled, protocols_activated):
        self.cognition_protocol_reports.append((session_id, list(protocols_enabled), list(protocols_activated)))
        return self.exists

    def save_protocol_execution_report(self, session_id, protocol, **fields):
        self.participation.append((session_id, protocol, fields))
        return True

    def save_protocol_execution_metrics(self, session_id, protocol, metrics):
        self.metrics.append((session_id, protocol, list(metrics)))
        return self.metrics_ok


class FakeEvaluator(ProtocolEvaluator):
    def __init__(self, name, passed=("M1", "M2"), failed=(), raises=False):
        self.name, self.passed, self.failed, self.raises, self.calls = name, list(passed), list(failed), raises, []

    def evaluate(self, session_id):
        self.calls.append(session_id)
        if self.raises:
            raise RuntimeError("boom")
        return Evaluation(passed=self.passed, failed=self.failed)


def make(spans, writer, evaluators, detectors=None):
    return CognitionProtocolsWorker(
        rabbitmq_url="amqp://x", input_queue="q", reader=FakeReader(spans), writer=writer, evaluators=evaluators, detectors=detectors
    )


async def run(worker, session="sess"):
    return await worker.handle_message(BaseQueueMessage(session_id=session))


async def test_an_activated_protocol_is_recorded_then_evaluated():
    writer, accord = FakeWriter(), FakeEvaluator("accord")
    assert await run(make(ACTIVATED, writer, [accord])) is True
    assert writer.cognition_protocol_reports == [("sess", ["accord"], ["accord"])]
    assert [p for _, p, _ in writer.participation] == ["accord"]
    assert accord.calls == ["sess"]
    assert writer.metrics == [("sess", "accord", ["M1", "M2"])]


async def test_a_protocol_that_was_only_enabled_is_not_evaluated():
    writer, accord = FakeWriter(), FakeEvaluator("accord")
    assert await run(make(ENABLED_ONLY, writer, [accord])) is True
    assert writer.cognition_protocol_reports == [("sess", ["accord"], [])]
    assert writer.participation == []  # no execution report either: only activated protocols get one
    assert accord.calls == [] and writer.metrics == []


async def test_a_session_without_any_protocol_gets_an_empty_cognition_protocol_report_and_nothing_is_evaluated():
    writer, accord = FakeWriter(), FakeEvaluator("accord")
    assert await run(make(NOTHING, writer, [accord])) is True
    assert writer.cognition_protocol_reports == [("sess", [], [])]  # recorded as checked, with empty lists
    assert writer.participation == [] and writer.metrics == [] and accord.calls == []


async def test_an_activated_protocol_without_an_evaluator_is_only_detected():
    writer = FakeWriter()
    assert await run(make(ACTIVATED, writer, [])) is True
    assert writer.cognition_protocol_reports == [("sess", ["accord"], ["accord"])] and writer.metrics == []


async def test_a_session_missing_from_the_graph_is_an_error_and_is_not_evaluated():
    writer, accord = FakeWriter(exists=False), FakeEvaluator("accord")
    assert await run(make(ACTIVATED, writer, [accord]), "ghost") is None
    assert accord.calls == []


async def test_nothing_applying_clears_the_reports_earlier_metrics():
    writer = FakeWriter()
    assert await run(make(ACTIVATED, writer, [FakeEvaluator("accord", passed=[], failed=["skipped"])])) is True
    assert writer.metrics == [("sess", "accord", [])]  # the report always holds the latest run


async def test_a_failing_evaluator_fails_the_message_but_not_the_other_protocols():
    class Tooly(ProtocolDetector):
        name = "tooly"

        def detect(self, context):
            return ProtocolFinding("tooly", enabled=True, activated=True, enabled_by_agent={"sre": ["t"]}, activated_by_agent={"sre": ["t"]})

    writer = FakeWriter()
    tooly = FakeEvaluator("tooly", passed=["T1"])
    worker = make(ACTIVATED, writer, [FakeEvaluator("accord", raises=True), tooly], detectors=[*builtin_detectors(), Tooly()])
    assert await run(worker) is None  # the base worker sees an error
    assert writer.cognition_protocol_reports == [("sess", ["accord", "tooly"], ["accord", "tooly"])]  # detection was still recorded
    assert writer.metrics == [("sess", "tooly", ["T1"])]  # and the other protocol was still evaluated


async def test_a_failed_metrics_write_fails_the_message():
    assert await run(make(ACTIVATED, FakeWriter(metrics_ok=False), [FakeEvaluator("accord")])) is None


async def test_evaluators_may_be_given_as_a_dict():
    writer, accord = FakeWriter(), FakeEvaluator("accord")
    assert await run(make(ACTIVATED, writer, {"accord": accord})) is True
    assert accord.calls == ["sess"]
