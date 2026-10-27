#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""The agent that looks for cognitive failures in one session.

The worker has already fetched the whole trajectory and written it to a ``TraceFile``. The agent
reads it only through tools (``list_steps``, ``read_step``, ``grep``), so it can decide which parts
of a long trace to read, and it ends by calling ``submit_detections``, whose arguments are the
``DetectionAnswer`` schema. It has no client for the API or the graph, and writing the reports is
the worker's job. ``investigate`` is the only entry point.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from cognitive_failure_worker.detector import (
    DetectionAnswer,
    DetectionResult,
    DetectorError,
    parse_detections,
    render_failures,
)
from cognitive_failure_worker.trace_file import TraceFile

logger = logging.getLogger(__name__)

MAX_TURNS = 15  # model calls per session; the last one must submit
MAX_TOOL_RESULT_CHARS = 8000
OVERVIEW_STEPS = 60  # steps listed in the first message; the agent lists the rest itself
SUBMIT = "submit_detections"

SYSTEM_PROMPT = f"""\
You review traces of LLM-based multi-agent systems for cognitive failures from a fixed taxonomy.

The trace is stored outside this conversation. You read it with tools: list_steps (the steps with their \
ids and sizes), read_step (a window of one step's input and output), grep (a regular expression over all \
the steps' texts). Decide what to read: use the failures' signs and heuristics to choose, grep for the \
evidence they ask for, and read the steps around it. Do not try to read everything.

Report a failure only when the trace itself shows what its detection heuristic asks for, and say at which \
step. Most traces show few failures or none: an empty answer is normal and correct. Do not report a \
failure for style, for minor imperfections, or because it merely could have happened.

When you are done, call {SUBMIT} once, with no detections if you found none. You have at most {MAX_TURNS} \
turns; the last one must be {SUBMIT}."""

TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_steps",
            "description": "List the steps of the trace: position, id, kind, name, agent, sizes and the start of the input.",
            "parameters": {
                "type": "object",
                "properties": {
                    "offset": {"type": "integer", "description": "Position of the first step.", "default": 0},
                    "limit": {"type": "integer", "description": "How many steps (max 200).", "default": 50},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_step",
            "description": "Read a window of the input and/or output text of one step. Long texts continue at the offset it gives.",
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "Id of the step, as listed."},
                    "field": {"type": "string", "enum": ["input", "output", "both"], "default": "both"},
                    "offset": {"type": "integer", "description": "First character to read.", "default": 0},
                    "length": {"type": "integer", "description": "Characters to read (max 8000).", "default": 4000},
                },
                "required": ["call_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Case-insensitive regular expression search over the texts of all steps. Returns step id, field, position and context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regular expression."},
                    "field": {"type": "string", "enum": ["input", "output", "both"], "default": "both"},
                    "max_matches": {"type": "integer", "default": 20},
                    "context": {"type": "integer", "description": "Characters around each match.", "default": 100},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": SUBMIT,
            "description": "Give the final answer: the failures the trace shows, possibly none. Ends the review.",
            "parameters": DetectionAnswer.model_json_schema(),
        },
    },
]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON text, as the model wrote it


@dataclass(frozen=True)
class ChatReply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


# messages, tools, name of the tool the model must call (or None) -> the model's reply
Chat = Callable[[list[dict[str, Any]], list[dict[str, Any]], str | None], ChatReply]


def _assistant_message(reply: ChatReply) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": reply.content or None}
    if reply.tool_calls:
        message["tool_calls"] = [
            {"id": c.id, "type": "function", "function": {"name": c.name, "arguments": c.arguments}}
            for c in reply.tool_calls
        ]
    return message


def _run_tool(trace: TraceFile, call: ToolCall) -> str:
    """The result of a read tool, as text for the model. A bad call is an answer, not an error."""
    try:
        arguments = json.loads(call.arguments or "{}")
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be a JSON object")
        if call.name == "list_steps":
            result = trace.list_steps(**arguments)
        elif call.name == "read_step":
            result = trace.read_step(**arguments)
        elif call.name == "grep":
            result = trace.grep(**arguments)
        else:
            return f"Unknown tool {call.name!r}. Tools: list_steps, read_step, grep, {SUBMIT}."
    except (ValueError, TypeError) as exc:  # bad JSON, missing/unknown argument, not a number
        return f"Bad arguments for {call.name}: {exc}"
    if len(result) > MAX_TOOL_RESULT_CHARS:
        result = result[:MAX_TOOL_RESULT_CHARS] + "\n[result cut: ask for less]"
    return result


def _first_message(trace: TraceFile, session_id: Any, failures: Sequence[Mapping[str, Any]]) -> str:
    return (
        f"## Failures to look for\n\n{render_failures(failures)}\n\n"
        f"## Trace of session {session_id}\n\n{len(trace)} steps. The first ones:\n"
        f"{trace.list_steps(0, OVERVIEW_STEPS)}\n\n"
        f"Investigate with the tools, then call {SUBMIT}."
    )


def investigate(
    trajectory: Mapping[str, Any],
    failures: Sequence[Mapping[str, Any]],
    chat: Chat,
    max_turns: int = MAX_TURNS,
) -> DetectionResult:
    """The cognitive failures of ``failures`` that the trajectory shows.

    The trajectory is written to a temporary file for the agent to read and the file is deleted
    before this returns, even on an error. Raises ``DetectorError`` if the agent does not submit a
    usable answer within ``max_turns`` model calls; the caller decides what that means.
    """
    codes = {c["code"] for c in failures}
    prompt_tokens = completion_tokens = 0
    with TraceFile(trajectory) as trace:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _first_message(trace, trajectory.get("session_id"), failures)},
        ]
        for turn in range(1, max_turns + 1):
            reply = chat(messages, TOOLS, SUBMIT if turn == max_turns else None)
            prompt_tokens += reply.prompt_tokens
            completion_tokens += reply.completion_tokens
            messages.append(_assistant_message(reply))

            if not reply.tool_calls:  # an answer in plain text is accepted if it is the expected JSON
                try:
                    detections = parse_detections(reply.content, codes, trace.step_ids)
                    return DetectionResult(detections, prompt_tokens, completion_tokens, turn)
                except DetectorError:
                    messages.append({"role": "user", "content": f"Call {SUBMIT} with your answer."})
                    continue

            for call in reply.tool_calls:
                if call.name == SUBMIT:
                    try:
                        detections = parse_detections(call.arguments, codes, trace.step_ids)
                    except DetectorError as exc:
                        messages.append({"role": "tool", "tool_call_id": call.id, "content": f"Rejected: {exc}"})
                    else:
                        return DetectionResult(detections, prompt_tokens, completion_tokens, turn)
                else:
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": _run_tool(trace, call)})
        raise DetectorError(f"no usable answer within {max_turns} turns")
