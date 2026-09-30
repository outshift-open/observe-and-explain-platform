#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
tests/demo_constants.py
=======================
Shared constants for the MCE demo and its functional tests.

Both ``demo.py`` and ``tests/test_demo_steps.py`` import from here so there
is a single source of truth for session IDs, expected metric values, and
fixture file paths.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Session / resource IDs
# ---------------------------------------------------------------------------

SESSION_ID = "76bc0800-8f02-416a-9ff3-f172e0ad68c2"

# The 13 LLM call IDs present in metric_cache.json (used in demo steps 8-10, 13-15)
LLM_IDS = [
    "exec-llm-8bc52586b489a311",
    "exec-llm-882939976a2e4688",
    "exec-llm-8561ff1f4b666245",
    "exec-llm-218ff57256ffc4d4",
    "exec-llm-deb09987a4b1042e",
    "exec-llm-7ce5aa9ea4091f9a",
    "exec-llm-7e519c8646df3af5",
    "exec-llm-3e18cdaa5a94a9f1",
    "exec-llm-7216fe9320af5e00",
    "exec-llm-8e920b160f459f35",
    "exec-llm-ff7f6b4a4b260415",
    "exec-llm-c2ed51fb30f61f25",
    "exec-llm-498b0e53496c5eab",
]

# The 6 tool call IDs present in metric_cache.json
TOOL_IDS = [
    "exec-tool-511a455c9cbc7b1a",
    "exec-tool-7bf439d519ed598c",
    "exec-tool-ceb87028da96bdf3",
    "exec-tool-b1ac3aa48bd64c35",
    "exec-tool-1d10eab39855fb4a",
    "exec-tool-2400e854a33378a1",
]

# ---------------------------------------------------------------------------
# Fixture file paths
# ---------------------------------------------------------------------------

_TESTS_DIR = Path(__file__).parent
METRIC_CACHE_PATH = _TESTS_DIR.parent / "demo" / "scores.json"
LLM_CACHE_PATH = _TESTS_DIR / "data" / "llm_cache.json"

# ---------------------------------------------------------------------------
# Expected cached values (sourced from metric_cache.json, verified offline)
# ---------------------------------------------------------------------------

SESSION_AR_VALUE = 0.8571428571428571  # AnswerRelevancy for SESSION_ID
LLM_AR_VALUE = 0.8285714285714286  # AnswerRelevancy for exec-llm-8bc52586b489a311
SESSION_TOKEN_COUNT = 27490  # TokenCount for SESSION_ID
MAX_LLM_AR_VALUE = 0.8571428571428571  # max AnswerRelevancy across 13 LLM calls
