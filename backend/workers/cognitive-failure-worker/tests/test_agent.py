#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json

import pytest
from conftest import TRAJECTORY

from cognitive_failure_worker import agent, trace_file
from cognitive_failure_worker.agent import SUBMIT, ChatReply, ToolCall, investigate
from cognitive_failure_worker.detector import DetectorError
from cognitive_failure_worker.failures import select_failures

FAILURES = select_failures(["IC-2", "CC-3"])


def _tool(name, **arguments):
    return ChatReply(tool_calls=[ToolCall(f"id-{name}", name, json.dumps(arguments))], prompt_tokens=10, completion_tokens=2)


def _submit(*items):
    return _tool(SUBMIT, detections=list(items))


def _item(code="IC-2", confidence="medium", reasoning="why", call_id="llmcall:1"):
    return {"code": code, "confidence": confidence, "reasoning": reasoning, "call_id": call_id}


class Script:
    """A model that replies from a list and records what it was shown."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, messages, tools, force):
        self.calls.append(([dict(m) for m in messages], tools, force))
        return self.replies.pop(0)


def test_the_first_message_has_the_definitions_and_the_start_of_the_trace():
    chat = Script(_submit())

    investigate(TRAJECTORY, FAILURES, chat)

    messages, tools, force = chat.calls[0]
    system, user = messages[0]["content"], messages[1]["content"]
    assert "### IC-2" in user and "### CC-3" in user and "### IR-1" not in user
    assert "Detect when:" in user and "2 steps" in user and "llmcall:1" in user
    assert "empty answer is normal" in system and SUBMIT in system
    assert {t["function"]["name"] for t in tools} == {"list_steps", "read_step", "grep", SUBMIT}
    assert force is None


def test_the_agent_reads_with_tools_then_submits():
    chat = Script(
        _tool("grep", pattern="paris"),
        _tool("read_step", call_id="llmcall:1", field="input"),
        _submit(_item("CC-3", "low", "unreconciled", "toolcall:2")),
    )

    result = investigate(TRAJECTORY, FAILURES, chat)

    assert [d.as_dict() for d in result.detections] == [
        {"code": "CC-3", "confidence": "low", "reasoning": "unreconciled", "call_id": "toolcall:2"}
    ]
    assert (result.turns, result.prompt_tokens, result.completion_tokens) == (3, 30, 6)
    grep_result = chat.calls[1][0][-1]
    assert grep_result["role"] == "tool" and grep_result["tool_call_id"] == "id-grep"
    assert "llmcall:1 input" in grep_result["content"]
    assert "Book a train to Paris" in chat.calls[2][0][-1]["content"]


def test_an_assistant_message_carries_its_tool_calls_for_the_next_turn():
    chat = Script(_tool("list_steps"), _submit())

    investigate(TRAJECTORY, FAILURES, chat)

    assistant = chat.calls[1][0][-2]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["function"]["name"] == "list_steps"


def test_the_last_turn_is_forced_to_submit():
    chat = Script(_tool("list_steps"), _tool("list_steps"), _submit())

    investigate(TRAJECTORY, FAILURES, chat, max_turns=3)

    assert [force for *_, force in chat.calls] == [None, None, SUBMIT]


def test_no_answer_within_the_turns_is_an_error():
    chat = Script(*[_tool("list_steps")] * 3)

    with pytest.raises(DetectorError, match="3 turns"):
        investigate(TRAJECTORY, FAILURES, chat, max_turns=3)


def test_a_rejected_submission_is_answered_so_the_agent_can_try_again():
    chat = Script(ChatReply(tool_calls=[ToolCall("s1", SUBMIT, "not json")]), _submit(_item()))

    result = investigate(TRAJECTORY, FAILURES, chat)

    rejection = chat.calls[1][0][-1]
    assert rejection["tool_call_id"] == "s1" and rejection["content"].startswith("Rejected")
    assert len(result.detections) == 1


def test_a_plain_text_answer_in_the_expected_json_is_accepted():
    chat = Script(ChatReply(content=json.dumps({"detections": [_item()]})))

    assert len(investigate(TRAJECTORY, FAILURES, chat).detections) == 1


def test_plain_text_that_is_not_an_answer_is_told_to_submit():
    chat = Script(ChatReply(content="Let me think."), _submit())

    result = investigate(TRAJECTORY, FAILURES, chat)

    assert SUBMIT in chat.calls[1][0][-1]["content"] and result.detections == []


def test_only_the_failures_asked_for_and_the_steps_of_the_trace_are_accepted():
    chat = Script(_submit(_item("IR-1"), _item("IC-2", call_id="made-up")))

    (detection,) = investigate(TRAJECTORY, FAILURES, chat).detections

    assert detection.code == "IC-2" and detection.call_id is None


@pytest.mark.parametrize(
    "call",
    [
        ToolCall("c", "read_step", "not json"),
        ToolCall("c", "read_step", "[]"),
        ToolCall("c", "read_step", "{}"),  # call_id missing
        ToolCall("c", "grep", '{"pattern": "x", "path": "/etc/passwd"}'),  # no such argument
        ToolCall("c", "list_steps", '{"offset": "abc"}'),
        ToolCall("c", "delete_everything", "{}"),
    ],
)
def test_a_bad_tool_call_is_answered_not_raised(call):
    chat = Script(ChatReply(tool_calls=[call]), _submit())

    investigate(TRAJECTORY, FAILURES, chat)

    assert chat.calls[1][0][-1]["role"] == "tool"


def test_a_long_tool_result_is_cut(monkeypatch):
    monkeypatch.setattr(agent, "MAX_TOOL_RESULT_CHARS", 50)
    chat = Script(_tool("read_step", call_id="llmcall:1", length=4000), _submit())

    investigate({"session_id": "s", "steps": [{**TRAJECTORY["steps"][0], "input_text": "x" * 500}]}, FAILURES, chat)

    assert chat.calls[1][0][-1]["content"].endswith("[result cut: ask for less]")


def test_the_trace_file_exists_while_the_agent_works_and_is_gone_after(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_file.tempfile, "tempdir", str(tmp_path))
    seen = []

    def chat(messages, tools, force):
        seen.append([p.name for p in tmp_path.iterdir()])
        return _submit()

    investigate(TRAJECTORY, FAILURES, chat)

    assert len(seen[0]) == 1 and seen[0][0].startswith(trace_file.DIR_PREFIX)
    assert list(tmp_path.iterdir()) == []


def test_the_trace_file_is_gone_when_the_model_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_file.tempfile, "tempdir", str(tmp_path))

    def chat(messages, tools, force):
        raise RuntimeError("endpoint down")

    with pytest.raises(RuntimeError):
        investigate(TRAJECTORY, FAILURES, chat)

    assert list(tmp_path.iterdir()) == []


def test_a_long_trace_lists_only_the_first_steps_in_the_first_message(monkeypatch):
    monkeypatch.setattr(agent, "OVERVIEW_STEPS", 3)
    steps = [{**TRAJECTORY["steps"][0], "call_id": f"llmcall:{i}"} for i in range(10)]
    chat = Script(_submit())

    investigate({"session_id": "s", "steps": steps}, FAILURES, chat)

    user = chat.calls[0][0][1]["content"]
    assert "10 steps" in user and "llmcall:2" in user and "llmcall:3" not in user and "next offset 3" in user
