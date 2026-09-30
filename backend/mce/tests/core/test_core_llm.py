#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.engine.llm.LLMService (v2 singleton)."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from mce.engine.llm import LLMService


@pytest.fixture(autouse=True)
def reset_singleton():
    """Ensure LLMService singleton is cleared between tests."""
    LLMService._instance = None
    yield
    LLMService._instance = None


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_default_mode_is_live():
    svc = LLMService()
    assert svc.mode == "live"


def test_custom_mode():
    svc = LLMService(mode="replay")
    assert svc.mode == "replay"


def test_cache_path_default():
    svc = LLMService()
    assert svc.cache_path == Path("llm_cache.json")


def test_cache_path_custom():
    svc = LLMService(cache_path="/tmp/my_cache.json")
    assert svc.cache_path == Path("/tmp/my_cache.json")


def test_live_mode_no_cache_load(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"key": {"output": "hello"}}')
    svc = LLMService(mode="live", cache_path=str(cache_file))
    # Live mode does not load cache
    assert svc.cache == {}


def test_replay_mode_loads_cache(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"k": {"output": "v"}}')
    svc = LLMService(mode="replay", cache_path=str(cache_file))
    assert svc.cache["k"]["output"] == "v"


def test_record_mode_loads_cache(tmp_path):
    cache_file = tmp_path / "cache.json"
    cache_file.write_text('{"k": {"output": "v"}}')
    svc = LLMService(mode="record", cache_path=str(cache_file))
    assert "k" in svc.cache


def test_replay_mode_missing_file_starts_empty(tmp_path):
    svc = LLMService(mode="replay", cache_path=str(tmp_path / "nonexistent.json"))
    assert svc.cache == {}


def test_replay_mode_invalid_json_starts_empty(tmp_path):
    cache_file = tmp_path / "bad.json"
    cache_file.write_text("not json!!!")
    svc = LLMService(mode="replay", cache_path=str(cache_file))
    assert svc.cache == {}


# ---------------------------------------------------------------------------
# Singleton / configure
# ---------------------------------------------------------------------------


def test_get_instance_creates_singleton():
    svc1 = LLMService.get_instance()
    svc2 = LLMService.get_instance()
    assert svc1 is svc2


def test_configure_replaces_instance():
    svc1 = LLMService.get_instance()
    LLMService.configure(mode="replay", cache_path="/tmp/y.json")
    svc2 = LLMService._instance
    assert svc2 is not svc1
    assert svc2.mode == "replay"


# ---------------------------------------------------------------------------
# _hash_prompt
# ---------------------------------------------------------------------------


def test_hash_prompt_deterministic():
    svc = LLMService()
    h1 = svc._hash_prompt("hello", "gpt-4")
    h2 = svc._hash_prompt("hello", "gpt-4")
    assert h1 == h2


def test_hash_prompt_different_for_different_input():
    svc = LLMService()
    h1 = svc._hash_prompt("hello", "gpt-4")
    h2 = svc._hash_prompt("world", "gpt-4")
    assert h1 != h2


def test_hash_prompt_different_for_different_model():
    svc = LLMService()
    h1 = svc._hash_prompt("hello", "gpt-4")
    h2 = svc._hash_prompt("hello", "gpt-3.5-turbo")
    assert h1 != h2


# ---------------------------------------------------------------------------
# get_completion — replay mode
# ---------------------------------------------------------------------------


def test_replay_returns_cached_value(tmp_path):
    svc = LLMService(mode="replay", cache_path=str(tmp_path / "c.json"))
    key = svc._hash_prompt("test prompt", "gpt-4o")
    svc.cache[key] = {"output": "cached answer"}
    result = svc.get_completion("test prompt", model="gpt-4o")
    assert result == "cached answer"


def test_replay_miss_raises_keyerror(tmp_path):
    svc = LLMService(mode="replay", cache_path=str(tmp_path / "c.json"))
    with pytest.raises(KeyError, match="Replay cache miss"):
        svc.get_completion("unknown prompt", model="gpt-4o")


# ---------------------------------------------------------------------------
# get_completion — live mode
# ---------------------------------------------------------------------------


def test_live_mode_calls_litellm():
    svc = LLMService(mode="live", api_key="test-key", base_url="https://llm.example")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "live answer"
    with patch("mce.engine.llm._OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = mock_response
        result = svc.get_completion("q", model="gpt-4o")
        assert result == "live answer"
        mock_cls.assert_called_once_with(
            api_key="test-key",
            base_url="https://llm.example",
        )
        mock_cls.return_value.chat.completions.create.assert_called_once()


def test_live_mode_with_system_prompt():
    svc = LLMService(mode="live", api_key="test-key")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "answer"
    with patch("mce.engine.llm._OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = mock_response
        svc.get_completion("q", model="gpt-4o", system_prompt="be helpful")
        call_args = mock_cls.return_value.chat.completions.create.call_args[1][
            "messages"
        ]
        assert any(m["role"] == "system" for m in call_args)


def test_live_mode_no_litellm_raises():
    svc = LLMService(mode="live", api_key="test-key")
    with patch("mce.engine.llm._OpenAI", None):
        with pytest.raises(RuntimeError, match="openai package is not installed"):
            svc.get_completion("q", model="gpt-4o")


def test_live_mode_litellm_exception_raises():
    svc = LLMService(mode="live", api_key="test-key")
    with patch("mce.engine.llm._OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.side_effect = Exception(
            "api error"
        )
        with pytest.raises(RuntimeError, match="LLM call failed"):
            svc.get_completion("q", model="gpt-4o")


# ---------------------------------------------------------------------------
# get_completion — record mode
# ---------------------------------------------------------------------------


def test_record_mode_saves_to_cache(tmp_path):
    cache_file = tmp_path / "rec.json"
    svc = LLMService(mode="record", cache_path=str(cache_file), api_key="test-key")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "recorded answer"
    with patch("mce.engine.llm._OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = mock_response
        result = svc.get_completion("prompt", model="gpt-4o")
        assert result == "recorded answer"
        key = svc._hash_prompt("prompt", "gpt-4o")
        assert key in svc.cache
        assert cache_file.exists()


def test_record_mode_cache_entry_has_metadata(tmp_path):
    cache_file = tmp_path / "rec.json"
    svc = LLMService(mode="record", cache_path=str(cache_file), api_key="test-key")
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "answer"
    with patch("mce.engine.llm._OpenAI") as mock_cls:
        mock_cls.return_value.chat.completions.create.return_value = mock_response
        svc.get_completion("test", model="gpt-4o")
        key = svc._hash_prompt("test", "gpt-4o")
        entry = svc.cache[key]
        assert "prompt" in entry
        assert "output" in entry
        assert "model" in entry
        assert "timestamp" in entry
