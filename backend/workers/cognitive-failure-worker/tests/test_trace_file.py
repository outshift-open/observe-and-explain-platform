#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import os
import time
from pathlib import Path

import pytest
from conftest import TRAJECTORY, step

from cognitive_failure_worker import trace_file
from cognitive_failure_worker.trace_file import TraceFile, sweep_stale

LONG = {
    "session_id": "s",
    "steps": [
        step("llmcall:1", text_in="Book a train to Paris", text_out="Searching trains"),
        step("toolcall:2", "tool", "search", agent="", success=False, text_in="query: Paris", text_out="error 500"),
        step("llmcall:3", text_in="x" * 50 + " NEEDLE " + "y" * 50, text_out="z" * 20000),
    ],
}


# ---------------------------------------------------------------- the file's life


def test_the_file_exists_inside_the_block_and_is_deleted_after(tmp_path):
    with TraceFile(TRAJECTORY, directory=str(tmp_path)) as trace:
        path = trace.path
        assert path.is_file() and path.parent.parent == tmp_path
        assert (path.parent.stat().st_mode & 0o077) == 0  # private to the process owner

    assert not path.exists() and not path.parent.exists()
    assert list(tmp_path.iterdir()) == []


def test_the_file_is_deleted_when_the_block_fails(tmp_path):
    with pytest.raises(RuntimeError):
        with TraceFile(TRAJECTORY, directory=str(tmp_path)):
            raise RuntimeError("boom")

    assert list(tmp_path.iterdir()) == []


def test_the_file_is_deleted_when_writing_it_fails(tmp_path):
    with pytest.raises(KeyError):
        with TraceFile({"steps": [{"kind": "llm"}]}, directory=str(tmp_path)):  # no call_id
            pass

    assert list(tmp_path.iterdir()) == []


def test_stale_directories_are_swept_and_fresh_ones_kept(tmp_path):
    stale, fresh = tmp_path / f"{trace_file.DIR_PREFIX}old", tmp_path / f"{trace_file.DIR_PREFIX}new"
    other = tmp_path / "unrelated"
    for path in (stale, fresh, other):
        path.mkdir()
    old = time.time() - 2 * trace_file.STALE_AFTER_SECONDS
    os.utime(stale, (old, old))
    os.utime(other, (old, old))

    assert sweep_stale(str(tmp_path)) == 1
    assert not stale.exists() and fresh.exists() and other.exists()


def test_a_huge_text_is_cut_when_written(tmp_path, monkeypatch):
    monkeypatch.setattr(trace_file, "MAX_FIELD_CHARS", 1000)
    huge = {"steps": [step("llmcall:1", text_in="START " + "x" * 50000 + " END")]}

    with TraceFile(huge, directory=str(tmp_path)) as trace:
        text = trace.read_step("llmcall:1", "input", length=8000)

    assert "START" in text and "END" in text and "characters cut" in text
    assert len(text) < 2000


# ---------------------------------------------------------------- what the agent can ask


def test_list_steps_shows_ids_agents_failures_and_sizes():
    with TraceFile(LONG) as trace:
        text = trace.list_steps()

        assert trace.step_ids == {"llmcall:1", "toolcall:2", "llmcall:3"} and len(trace) == 3

    assert "#0 llmcall:1 | llm gpt-4o (agent: planner)" in text
    assert "#1 toolcall:2 | tool search [FAILED]" in text and "agent:" not in text.splitlines()[1]
    assert "out 20000 chars" in text and "'Book a train to Paris'" in text


def test_list_steps_pages():
    with TraceFile(LONG) as trace:
        first = trace.list_steps(0, 2)
        rest = trace.list_steps(2, 2)
        past = trace.list_steps(10)

    assert "llmcall:3" not in first and "next offset 2" in first
    assert "llmcall:3" in rest and "next offset" not in rest
    assert "has 3 steps" in past


def test_read_step_returns_a_window_and_where_to_continue():
    with TraceFile(LONG) as trace:
        first = trace.read_step("llmcall:3", "output", 0, 100)
        later = trace.read_step("llmcall:3", "output", 19950, 100)
        both = trace.read_step("llmcall:1")

    assert "chars 0-100 of 20000; continue at offset 100" in first and "z" * 100 in first
    assert "chars 19950-20000 of 20000]" in later and "continue" not in later
    assert "INPUT [" in both and "Book a train to Paris" in both and "OUTPUT [" in both


def test_read_step_refuses_an_unknown_step_or_field():
    with TraceFile(LONG) as trace:
        assert "Unknown step" in trace.read_step("nope")
        assert "field must be" in trace.read_step("llmcall:1", "everything")


def test_grep_finds_text_with_its_step_field_and_context():
    with TraceFile(LONG) as trace:
        text = trace.grep("needle", context=10)

    assert text.startswith("llmcall:3 input @51:") and "NEEDLE" in text


def test_grep_limits_its_matches_and_says_so():
    with TraceFile(LONG) as trace:
        text = trace.grep("z", "output", max_matches=3)

    assert len(text.splitlines()) == 4 and "narrow the pattern" in text


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [("(", "Invalid regular expression"), ("x" * 500, "too long"), ("nothing like this", "No match")],
)
def test_grep_answers_a_bad_search(pattern, expected):
    with TraceFile(LONG) as trace:
        assert expected in trace.grep(pattern)


def test_only_one_step_is_read_at_a_time(tmp_path):
    with TraceFile(LONG, directory=str(tmp_path)) as trace:
        assert all(isinstance(entry[1], int) for entry in trace._index)  # offsets, not texts
        assert not hasattr(trace, "_steps")
        assert Path(trace.path).stat().st_size > 20000
