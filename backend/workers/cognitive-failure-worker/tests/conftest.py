#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest


@pytest.fixture
def rabbit_url():
    return "amqp://guest:guest@localhost/"


def step(call_id, kind="llm", name="gpt-4o", agent="planner", success=True, text_in="in", text_out="out"):
    return {
        "transition_id": call_id.replace("call", "transition"),
        "call_id": call_id,
        "kind": kind,
        "name": name,
        "agent_id": agent,
        "success": success,
        "input_text": text_in,
        "output_text": text_out,
    }


TRAJECTORY = {
    "session_id": "session-1",
    "steps": [
        step("llmcall:1", text_in="Book a train to Paris", text_out="Searching trains"),
        step("toolcall:2", "tool", "search"),
    ],
}
