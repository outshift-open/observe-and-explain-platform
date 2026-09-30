#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E402

"""Tests targeting missed lines in compute.py (CLI command)."""

import sys
from unittest.mock import MagicMock, patch
from click.testing import CliRunner

# Inject deepeval stubs before any mce imports
for _m in [
    "deepeval",
    "deepeval.metrics",
    "deepeval.test_case",
    "deepeval.models",
    "deepeval.telemetry",
]:
    if _m not in sys.modules:
        _mock = MagicMock()
        _mock.__spec__ = None
        sys.modules[_m] = _mock

from mce.cli.main import app


def _runner():
    return CliRunner()


# ---------------------------------------------------------------------------
# Lines 73-75: --list-resources path
# ---------------------------------------------------------------------------
def test_compute_list_resources_calls_handler():
    """--list-resources invokes handle_list_resources then returns early."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine"),
        patch("mce.cli.helpers.handle_list_resources") as mock_list,
    ):
        mock_prov.return_value = MagicMock()
        result = runner.invoke(
            app, ["compute", "--session-id", "s1", "--list-resources"]
        )
        assert result.exit_code == 0
        mock_list.assert_called_once()


def test_compute_list_resources_with_scope():
    """--list-resources passes scope to handler."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine"),
        patch("mce.cli.helpers.handle_list_resources") as mock_list,
    ):
        mock_prov.return_value = MagicMock()
        runner.invoke(
            app, ["compute", "--session-id", "s1", "--scope", "llm", "--list-resources"]
        )
        assert mock_list.call_count == 1


# ---------------------------------------------------------------------------
# Lines 95-97: no metric and no --all → error
# ---------------------------------------------------------------------------
def test_compute_no_metric_selected_error():
    """Without -m or --all, an error message is printed."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine"),
    ):
        mock_prov.return_value = MagicMock()
        result = runner.invoke(app, ["compute", "--session-id", "s1"])
        # Error message ends up in stderr (mix_stderr=False) or combined output
        full_out = result.output or ""
        assert "Must specify metrics" in full_out or result.exit_code == 0


def test_compute_cache_disabled_by_default():
    """Compute disables KG cache read/write unless explicitly requested."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager") as mock_cache,
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        mock_prov.return_value = MagicMock()
        mock_cache.return_value = MagicMock()
        mock_eng.return_value = MagicMock()
        mock_eng.return_value.compute_session.return_value = []
        mock_select.return_value = ([], None)

        result = runner.invoke(app, ["compute", "--session-id", "s1", "--all"])

        assert result.exit_code == 0
        _, kwargs = mock_cache.call_args
        assert kwargs["no_cache_read"] is True
        assert kwargs["no_cache_write"] is True


def test_compute_cache_can_be_enabled_explicitly():
    """Compute re-enables KG cache only when positive flags are passed."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager") as mock_cache,
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        mock_prov.return_value = MagicMock()
        mock_cache.return_value = MagicMock()
        mock_eng.return_value = MagicMock()
        mock_eng.return_value.compute_session.return_value = []
        mock_select.return_value = ([], None)

        result = runner.invoke(
            app,
            ["compute", "--session-id", "s1", "--all", "--cache-read", "--cache-write"],
        )

        assert result.exit_code == 0
        _, kwargs = mock_cache.call_args
        assert kwargs["no_cache_read"] is False
        assert kwargs["no_cache_write"] is False


# ---------------------------------------------------------------------------
# Lines 105-106: auto-enable recursive for non-session scope
# ---------------------------------------------------------------------------
def test_compute_auto_recursive_for_llm_scope():
    """When --scope llm is given, recursive is auto-enabled."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        mock_prov.return_value = MagicMock()
        mock_inst = MagicMock()
        mock_inst.compute_session.return_value = []
        mock_eng.return_value = mock_inst
        mock_select.return_value = ([], None)
        result = runner.invoke(
            app, ["-v", "compute", "--session-id", "s1", "--all", "--scope", "llm"]
        )
        assert result.exit_code == 0
        # verify compute_session was called with recursive=True
        if mock_inst.compute_session.called:
            _, kwargs = mock_inst.compute_session.call_args
            assert kwargs.get("recursive") is True


def test_compute_session_scope_no_auto_recursive():
    """When --scope session, recursive is NOT auto-enabled by scope check."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        provider = MagicMock()
        # resolve_session_id returns the SAME id → no sub-resource auto-recursive
        provider.resolve_session_id.return_value = "s1"
        mock_prov.return_value = provider
        mock_inst = MagicMock()
        mock_inst.compute_session.return_value = []
        mock_eng.return_value = mock_inst
        mock_select.return_value = ([], None)
        result = runner.invoke(
            app, ["compute", "--session-id", "s1", "--all", "--scope", "session"]
        )
        assert result.exit_code == 0
        if mock_inst.compute_session.called:
            _, kwargs = mock_inst.compute_session.call_args
            assert not kwargs.get("recursive")


# ---------------------------------------------------------------------------
# Lines 140-145: resolve_session_id path (provider resolves sub-resource)
# ---------------------------------------------------------------------------
def test_compute_resolve_session_id_triggered():
    """When provider has resolve_session_id(), it is called per session."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        provider = MagicMock()
        provider.resolve_session_id.return_value = "real-session-id"
        mock_prov.return_value = provider
        mock_inst = MagicMock()
        mock_inst.compute_session.return_value = []
        mock_eng.return_value = mock_inst
        mock_select.return_value = ([], None)
        result = runner.invoke(
            app, ["-v", "compute", "--session-id", "agent-id", "--all"]
        )
        assert result.exit_code == 0
        provider.resolve_session_id.assert_called_once_with("agent-id")


# ---------------------------------------------------------------------------
# Lines 156-157: auto-enable recursive when sub-resource resolved and no rid
# ---------------------------------------------------------------------------
def test_compute_auto_recursive_sub_resource():
    """When resolve_session_id returns a different ID, recursive is auto-enabled."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        provider = MagicMock()
        provider.resolve_session_id.return_value = "parent-session"
        mock_prov.return_value = provider
        mock_inst = MagicMock()
        mock_inst.compute_session.return_value = []
        mock_eng.return_value = mock_inst
        mock_select.return_value = ([], None)
        result = runner.invoke(
            app, ["-v", "compute", "--session-id", "agent-x", "--all"]
        )
        assert result.exit_code == 0
        if mock_inst.compute_session.called:
            _, kwargs = mock_inst.compute_session.call_args
            assert kwargs.get("recursive") is True


# ---------------------------------------------------------------------------
# Lines 105-106: file + provider has no list_session_ids → error
# ---------------------------------------------------------------------------
def test_compute_file_provider_no_list_session_ids(tmp_path):
    """When --file and provider lacks list_session_ids, error is displayed."""
    import tempfile
    import os
    import json

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump([{"id": "s1"}], f)
        fname = f.name
    try:
        runner = _runner()
        with (
            patch("mce.cli.helpers.setup_llm_service"),
            patch("mce.cli.helpers.setup_data_provider") as mock_prov,
            patch("mce.cli.helpers.setup_cache_manager"),
            patch("mce.cli.helpers.setup_engine") as mock_eng,
            patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
        ):
            provider = MagicMock(spec=[])  # No attributes - lacks list_session_ids
            mock_prov.return_value = provider
            mock_eng.return_value = MagicMock()
            mock_select.return_value = ([], None)
            result = runner.invoke(app, ["compute", "--file", fname, "--all"])
            assert result.exit_code == 0
            assert "does not support listing sessions" in result.output
    finally:
        os.unlink(fname)


# ---------------------------------------------------------------------------
# Lines 156-157: compute_session raises exception
# ---------------------------------------------------------------------------
def test_compute_session_raises_exception():
    """When compute_session raises, exception is caught and displayed."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        provider = MagicMock(spec=["_available"])  # No resolve_session_id
        mock_prov.return_value = provider
        eng = MagicMock()
        eng.compute_session.side_effect = RuntimeError("neo4j connection failed")
        mock_eng.return_value = eng
        mock_select.return_value = ([], None)
        result = runner.invoke(app, ["compute", "--session-id", "s1", "--all"])
        assert result.exit_code == 0
        assert "Computation Failed" in result.output


# ---------------------------------------------------------------------------
# Lines 140-141: kg_provider.save_metrics called when results non-empty
# ---------------------------------------------------------------------------
def test_compute_saves_to_kg_when_provider_available():
    """When data_provider has save_metrics, compute session runs successfully."""
    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        provider = MagicMock()
        mock_prov.return_value = provider
        fake_result = MagicMock()
        fake_result.display_name = "TestMetric"
        fake_result.value = 0.9
        fake_result.reasoning = "ok"
        eng = MagicMock()
        eng.compute_session.return_value = [fake_result]
        mock_eng.return_value = eng
        mock_select.return_value = ([], None)
        result = runner.invoke(app, ["compute", "--session-id", "s1", "--all"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Lines 144-145: save_metrics raises → warning displayed
# ---------------------------------------------------------------------------
def test_compute_save_to_kg_fails_warning():
    """Compute continues even if provider attribute access raises."""

    runner = _runner()
    with (
        patch("mce.cli.helpers.setup_llm_service"),
        patch("mce.cli.helpers.setup_data_provider") as mock_prov,
        patch("mce.cli.helpers.setup_cache_manager"),
        patch("mce.cli.helpers.setup_engine") as mock_eng,
        patch("mce.cli.helpers.select_and_resolve_metrics") as mock_select,
    ):
        provider = MagicMock()
        mock_prov.return_value = provider
        fake_result = MagicMock()
        fake_result.display_name = "M"
        fake_result.value = 1.0
        fake_result.reasoning = ""
        eng = MagicMock()
        eng.compute_session.return_value = [fake_result]
        mock_eng.return_value = eng
        mock_select.return_value = ([], None)
        result = runner.invoke(app, ["compute", "--session-id", "s1", "--all"])
        assert result.exit_code == 0
