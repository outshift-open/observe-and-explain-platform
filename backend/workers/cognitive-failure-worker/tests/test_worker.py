#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
from types import SimpleNamespace

import oxp.client.failures  # noqa: F401  (so mocker can patch it)
import oxp.client.dal  # noqa: F401
import pytest
from conftest import TRAJECTORY
from worker_base.queue_message import BaseQueueMessage

from cognitive_failure_worker.agent import SUBMIT, ChatReply, ToolCall
from cognitive_failure_worker.worker import CognitiveFailureWorker


def _worker(rabbit_url, tmp_path=None, config=None, **kwargs):
    path = None
    if config is not None:
        path = tmp_path / "cognitive_failure_config.yaml"
        path.write_text(config, encoding="utf-8")
        path = str(path)
    return CognitiveFailureWorker(
        rabbit_url=rabbit_url,
        input_queue="test_input",
        llm_api_key="key",
        llm_model_name="gpt-4o",
        llm_base_model_url="https://example.test/v1",
        config_path=path,
        **kwargs,
    )


@pytest.fixture
def message():
    return BaseQueueMessage(job_id="job", session_id="session-1", workflow_id="wf")


@pytest.fixture
def kg(mocker):
    kg = mocker.Mock(spec=["execute", "execute_command", "ensure_connected"])
    mocker.patch.object(CognitiveFailureWorker, "_get_kg", return_value=kg)
    return kg


def _answer(*items):
    call = ToolCall("call-1", SUBMIT, json.dumps({"detections": list(items)}))
    return ChatReply(tool_calls=[call], prompt_tokens=10, completion_tokens=5)


# ---------------------------------------------------------------- config


def test_without_a_config_file_nothing_is_detected(rabbit_url):
    assert _worker(rabbit_url).failures == []


@pytest.mark.parametrize("text", ["", "failures:\n", "failures: []\n", "failures:\n  # - IR-1\n"])
def test_an_empty_config_detects_nothing(rabbit_url, tmp_path, text):
    assert _worker(rabbit_url, tmp_path, text).failures == []


def test_the_configured_failures_are_loaded(rabbit_url, tmp_path):
    worker = _worker(rabbit_url, tmp_path, "failures:\n  - ic-2\n  - CC-3\n")

    assert [c["code"] for c in worker.failures] == ["IC-2", "CC-3"]


def test_an_unknown_failure_stops_the_worker_at_startup(rabbit_url, tmp_path):
    with pytest.raises(ValueError, match="IC-99"):
        _worker(rabbit_url, tmp_path, "failures:\n  - IC-2\n  - IC-99\n")


def test_an_unknown_setting_stops_the_worker_at_startup(rabbit_url, tmp_path):
    with pytest.raises(ValueError, match="failure"):
        _worker(rabbit_url, tmp_path, "failure:\n  - IC-2\n")


def test_a_missing_config_file_stops_the_worker_at_startup(rabbit_url, tmp_path):
    with pytest.raises(FileNotFoundError):
        CognitiveFailureWorker(rabbit_url=rabbit_url, input_queue="q", config_path=str(tmp_path / "nope.yaml"))


def test_the_shipped_example_config_loads(rabbit_url):
    from pathlib import Path

    example = Path(__file__).resolve().parents[3] / "cognitive_failure_config.yaml"
    worker = CognitiveFailureWorker(rabbit_url=rabbit_url, input_queue="q", config_path=str(example))

    assert {c["code"] for c in worker.failures} == {
        "IR-1",
        "IC-1",
        "IC-2",
        "IE-1",
        "DR-2",
        "DC-3",
        "DC-4",
        "DE-1",
        "CC-3",
        "CE-1",
    }


# ---------------------------------------------------------------- messages


@pytest.mark.asyncio
async def test_detections_are_written_and_the_message_is_forwarded(
    rabbit_url, tmp_path, kg, message, mocker
):
    mocker.patch("oxp.client.dal.get_session_trajectory", return_value=TRAJECTORY)
    write = mocker.patch("oxp.client.failures.write_cognitive_failure_reports", return_value=1)
    worker = _worker(rabbit_url, tmp_path, "failures: [IC-2]\n")
    mocker.patch.object(
        worker,
        "_chat",
        return_value=_answer(
            {"code": "IC-2", "confidence": "high", "reasoning": "kept going", "call_id": "toolcall:2"}
        ),
    )

    assert await worker.handle_message(message) is True

    write.assert_called_once_with(
        kg, "session-1", [{"code": "IC-2", "confidence": "high", "reasoning": "kept going", "call_id": "toolcall:2"}]
    )
    (forwarded,) = worker.output_messages
    assert (forwarded.session_id, forwarded.job_id, forwarded.workflow_id) == ("session-1", "job", "wf")


@pytest.mark.asyncio
async def test_a_session_with_nothing_detected_writes_an_empty_list(rabbit_url, tmp_path, kg, message, mocker):
    mocker.patch("oxp.client.dal.get_session_trajectory", return_value=TRAJECTORY)
    write = mocker.patch("oxp.client.failures.write_cognitive_failure_reports", return_value=0)
    worker = _worker(rabbit_url, tmp_path, "failures: [IC-2]\n")
    mocker.patch.object(worker, "_chat", return_value=_answer())

    await worker.handle_message(message)

    write.assert_called_once_with(kg, "session-1", [])


@pytest.mark.asyncio
async def test_an_unusable_answer_writes_nothing_but_still_forwards(
    rabbit_url, tmp_path, kg, message, mocker
):
    mocker.patch("oxp.client.dal.get_session_trajectory", return_value=TRAJECTORY)
    write = mocker.patch("oxp.client.failures.write_cognitive_failure_reports")
    worker = _worker(rabbit_url, tmp_path, "failures: [IC-2]\n")
    mocker.patch.object(worker, "_chat", return_value=ChatReply(content="I cannot help with that"))

    assert await worker.handle_message(message) is True

    write.assert_not_called()
    assert len(worker.output_messages) == 1


@pytest.mark.asyncio
async def test_a_session_without_steps_is_skipped(rabbit_url, tmp_path, kg, message, mocker):
    mocker.patch("oxp.client.dal.get_session_trajectory", return_value={"session_id": "session-1", "steps": []})
    write = mocker.patch("oxp.client.failures.write_cognitive_failure_reports")
    worker = _worker(rabbit_url, tmp_path, "failures: [IC-2]\n")
    chat = mocker.patch.object(worker, "_chat")

    await worker.handle_message(message)

    chat.assert_not_called()
    write.assert_not_called()


@pytest.mark.asyncio
async def test_with_no_failure_configured_the_graph_and_the_model_are_not_touched(rabbit_url, kg, message, mocker):
    get_trajectory = mocker.patch("oxp.client.dal.get_session_trajectory")
    worker = _worker(rabbit_url)
    chat = mocker.patch.object(worker, "_chat")

    assert await worker.handle_message(message) is True

    get_trajectory.assert_not_called()
    chat.assert_not_called()
    kg.execute.assert_not_called()
    assert len(worker.output_messages) == 1


# ---------------------------------------------------------------- the model call


class _Client:
    """A model endpoint that answers with the given message."""

    def __init__(self, message=None):
        self.calls = []
        self.message = message or SimpleNamespace(content="done", tool_calls=None)
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=self.message)],
            usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        )


def test_the_tools_are_offered_and_the_usage_returned(rabbit_url):
    worker = _worker(rabbit_url)
    worker._client = _Client()
    tools = [{"type": "function", "function": {"name": "grep"}}]

    reply = worker._chat([{"role": "user", "content": "hi"}], tools, None)

    (call,) = worker._client.calls
    assert call["model"] == "gpt-4o" and call["temperature"] == 0
    assert call["tools"] == tools and "tool_choice" not in call
    assert (reply.content, reply.tool_calls, reply.prompt_tokens, reply.completion_tokens) == ("done", [], 7, 3)


def test_tool_calls_are_returned_as_they_came(rabbit_url):
    worker = _worker(rabbit_url)
    function = SimpleNamespace(name="grep", arguments='{"pattern": "x"}')
    worker._client = _Client(SimpleNamespace(content=None, tool_calls=[SimpleNamespace(id="c1", function=function)]))

    reply = worker._chat([], [], None)

    assert reply.content == "" and reply.tool_calls == [ToolCall("c1", "grep", '{"pattern": "x"}')]


def test_the_last_turn_forces_the_submit_tool(rabbit_url):
    worker = _worker(rabbit_url)
    worker._client = _Client()

    worker._chat([], [], SUBMIT)

    assert worker._client.calls[0]["tool_choice"] == {"type": "function", "function": {"name": SUBMIT}}


def test_a_failing_endpoint_raises(rabbit_url):
    worker = _worker(rabbit_url)
    worker._client = _Client()
    worker._client.chat.completions.create = lambda **kwargs: (_ for _ in ()).throw(RuntimeError("401 unauthorized"))

    with pytest.raises(RuntimeError, match="401"):
        worker._chat([], [], None)


def test_stale_trace_files_are_swept_at_startup(rabbit_url, mocker):
    sweep = mocker.patch("cognitive_failure_worker.worker.sweep_stale")

    _worker(rabbit_url)

    sweep.assert_called_once()
