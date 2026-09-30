#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for cli/helpers/resource_lister.py and cli_handlers.py."""

from unittest.mock import MagicMock
from mce.cli.helpers.resource_lister import list_sessions, list_agents, list_llm_calls
from mce.cli.helpers.cli_handlers import handle_list_resources


class TestListSessions:
    def test_returns_list_on_success(self):
        mock_kg = MagicMock()
        mock_kg.list_sessions.return_value = [{"session_id": "s1"}]
        result = list_sessions(mock_kg)
        assert result == [{"session_id": "s1"}]

    def test_returns_empty_on_exception(self):
        mock_kg = MagicMock()
        mock_kg.list_sessions.side_effect = Exception("db error")
        result = list_sessions(mock_kg)
        assert result == []


class TestListAgents:
    def test_returns_agents(self):
        mock_kg = MagicMock()
        mock_kg.list_agents.return_value = [{"agent_id": "a1"}]
        assert list_agents(mock_kg, "s1") == [{"agent_id": "a1"}]

    def test_returns_empty_on_exception(self):
        mock_kg = MagicMock()
        mock_kg.list_agents.side_effect = Exception("fail")
        assert list_agents(mock_kg, "s1") == []


class TestListLlmCalls:
    def test_returns_calls_when_method_exists(self):
        mock_kg = MagicMock()
        mock_kg.list_llm_calls.return_value = [{"call_id": "c1"}]
        assert list_llm_calls(mock_kg, "s1") == [{"call_id": "c1"}]

    def test_returns_empty_when_method_absent(self):
        mock_kg = MagicMock(spec=[])  # no list_llm_calls attribute
        result = list_llm_calls(mock_kg, "s1")
        assert result == []

    def test_returns_empty_on_exception(self):
        mock_kg = MagicMock()
        mock_kg.list_llm_calls.side_effect = Exception("fail")
        assert list_llm_calls(mock_kg, "s1") == []


class TestHandleListResources:
    def test_no_provider_prints_error(self, capsys):
        handle_list_resources(None, "session")
        captured = capsys.readouterr()
        assert "requires Neo4j" in captured.err

    def test_session_scope_lists_sessions(self, capsys):
        mock_kg = MagicMock()
        mock_kg.list_sessions.return_value = [{"session_id": "s1", "name": "Test"}]
        handle_list_resources(mock_kg, "session")
        captured = capsys.readouterr()
        assert "s1" in captured.out

    def test_agent_scope_without_session_id_prints_error(self, capsys):
        handle_list_resources(MagicMock(), "agent", session_id=None)
        captured = capsys.readouterr()
        assert "session-id required" in captured.err

    def test_agent_scope_lists_agents(self, capsys):
        mock_kg = MagicMock()
        mock_kg.list_agents.return_value = [{"agent_id": "a1", "name": "AgentX"}]
        handle_list_resources(mock_kg, "agent", session_id=("s1",))
        captured = capsys.readouterr()
        assert "a1" in captured.out

    def test_llm_scope_without_session_id_prints_error(self, capsys):
        handle_list_resources(MagicMock(), "llm", session_id=None)
        captured = capsys.readouterr()
        assert "session-id required" in captured.err

    def test_llm_scope_lists_calls(self, capsys):
        mock_kg = MagicMock()
        mock_kg.list_llm_calls.return_value = [
            {"call_id": "c1", "model": "gpt-4", "timestamp": "2024-01-01"}
        ]
        handle_list_resources(mock_kg, "llm", session_id=("s1",))
        captured = capsys.readouterr()
        assert "c1" in captured.out

    def test_unknown_scope_prints_not_implemented(self, capsys):
        handle_list_resources(MagicMock(), "unknown_scope")
        captured = capsys.readouterr()
        assert "not yet implemented" in captured.out
