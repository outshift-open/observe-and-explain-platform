#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
tests/conftest.py
=================
Session-wide pytest configuration and fixtures shared across all test modules.
"""

import pytest
from mce.engine.llm import LLMService, ErrorLLMService


@pytest.fixture(autouse=True)
def block_live_llm_calls():
    """Guard against unexpected live LLM calls in every test.

    Installs :class:`~mce.engine.llm.ErrorLLMService` as the active
    ``LLMService`` singleton before each test and restores the previous
    instance afterwards.

    Any code path that reaches ``LLMService.get_completion()`` without an
    explicit ``--llm-mode replay`` (or equivalent ``LLMService.configure()``)
    call will raise ``RuntimeError`` immediately, making the test failure
    explicit instead of silently returning a mock string or making a live API
    call.

    Tests that need LLM evaluation opt in by configuring the service in replay
    mode — typically via the CLI flags ``--llm-mode replay --llm-cache <path>``
    inside a ``CliRunner.invoke()`` call.  That call replaces the singleton for
    the duration of the invocation; this fixture then restores the error guard
    once the test finishes.

    Tests that must guarantee no LLM call is ever made can also pass
    ``--llm-mode error`` explicitly; ``setup_llm_service`` will install
    ``ErrorLLMService`` directly in that case.
    """
    orig = LLMService._instance
    LLMService._instance = ErrorLLMService()
    yield
    LLMService._instance = orig


def pytest_collection_modifyitems(config, items):
    """Auto-skip ``@pytest.mark.ollama`` tests unless explicitly selected.

    Running plain ``pytest`` never triggers the slow Ollama evaluation tests.
    To run them, pass ``-m ollama``.
    """
    markexpr = getattr(config.option, "markexpr", "") or ""
    if "ollama" not in markexpr:
        skip = pytest.mark.skip(
            reason="Ollama tests are opt-in — run with: pytest -m ollama"
        )
        for item in items:
            if item.get_closest_marker("ollama"):
                item.add_marker(skip)
