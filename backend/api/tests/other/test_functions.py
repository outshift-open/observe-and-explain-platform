#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Functional tests that print returned JSON to the terminal.

Run with:
    pytest tests/test_functions.py -v -s
"""

import json
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import oxp.ui
from oxp.db.database import init_oxp_db
from oxp.scripts.seed import seed_database_test

# ── Helpers ──────────────────────────────────────────────────────────────────


def to_epoch(timestamp: str) -> str:
    """Convert a human-readable timestamp to a Unix epoch string.

    Accepts the format used in otel_traces.csv, e.g.
    ``"2025-10-06 15:00:23.626769894"``.
    """
    # Truncate to whole seconds — sub-second precision is not needed
    truncated = timestamp[:19]  # "YYYY-MM-DD HH:MM:SS"
    dt = datetime.strptime(truncated, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return str(dt.timestamp())


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialise the oxp DB and seed OTEL data once for the module."""
    # When running in SQLite mode, use a sandbox file so threads can
    # share the database (SQLite :memory: is per-connection).
    if os.getenv("OXP_LOCAL", "true").lower() in ("true", "1", "yes"):
        sandbox = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox")
        os.makedirs(sandbox, exist_ok=True)
        os.environ["OXP_DB_PATH"] = os.path.join(sandbox, "oxp_test.db")
    init_oxp_db()
    seed_database_test()
    oxp.ui.reset_instance()  # re-create singleton with the correct DB path


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_get_sessions_no_params():
    result = oxp.ui.get_sessions()
    print("\n── get_sessions (no params) ──")
    print(json.dumps(result.model_dump(), indent=2))


def test_get_sessions_start_only():
    start = to_epoch("2025-10-06 15:04:28.000000000")
    result = oxp.ui.get_sessions(start_time=start)
    print(f"\n── get_sessions (start_time={start}) ──")
    print(json.dumps(result.model_dump(), indent=2))


def test_get_sessions_end_only():
    end = to_epoch("2025-10-06 16:00:00.000000000")
    result = oxp.ui.get_sessions(end_time=end)
    print(f"\n── get_sessions (end_time={end}) ──")
    print(json.dumps(result.model_dump(), indent=2))


def test_get_sessions_both_params():
    start = to_epoch("2025-10-06 14:00:00.000000000")
    end = to_epoch("2025-10-06 16:00:00.000000000")
    result = oxp.ui.get_sessions(start_time=start, end_time=end)
    print(f"\n── get_sessions (start_time={start}, end_time={end}) ──")
    print(json.dumps(result.model_dump(), indent=2))


# ── get_applications tests ─────────────────────────────────────────────────────


def test_get_applications_no_params():
    result = oxp.ui.get_applications()
    print("\n── get_applications (no params) ──")
    print(json.dumps(result.model_dump(), indent=2))
    assert isinstance(result.applications, list)


def test_get_applications_start_only():
    start = to_epoch("2025-10-06 15:04:28.000000000")
    result = oxp.ui.get_applications(start_time=start)
    print(f"\n── get_applications (start_time={start}) ──")
    print(json.dumps(result.model_dump(), indent=2))
    assert isinstance(result.applications, list)


def test_get_applications_end_only():
    end = to_epoch("2025-10-06 16:00:00.000000000")
    result = oxp.ui.get_applications(end_time=end)
    print(f"\n── get_applications (end_time={end}) ──")
    print(json.dumps(result.model_dump(), indent=2))
    assert isinstance(result.applications, list)


def test_get_applications_both_params():
    start = to_epoch("2025-10-06 14:00:00.000000000")
    end = to_epoch("2025-10-06 16:00:00.000000000")
    result = oxp.ui.get_applications(start_time=start, end_time=end)
    print(f"\n── get_applications (start_time={start}, end_time={end}) ──")
    print(json.dumps(result.model_dump(), indent=2))
    assert isinstance(result.applications, list)
