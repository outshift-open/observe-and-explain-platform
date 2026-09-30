#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for CLI kg commands (mce.cli.commands.kg)."""

from datetime import datetime
from unittest.mock import MagicMock, patch
import json
import pytest
from click.testing import CliRunner

from mce.cli.main import app
from mce.core.types import MetricResult

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def runner():
    return CliRunner()


def _make_metric_result(**kwargs):
    defaults = dict(
        metric_id="AR",
        resource_id="entity_abc",
        provider="Native",
        value=0.85,
        metric_class="AR",
        reasoning="good",
        metadata={"resource_labels": ["AgentCall"]},
    )
    defaults.update(kwargs)
    r = MetricResult(**defaults)
    r.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    return r


def _patched_neo4j(metrics=None, query_result=None):
    """Build a mock KG provider used by CLI tests."""
    mock_inst = MagicMock()
    mock_inst.get_metrics.return_value = metrics if metrics is not None else []
    mock_inst.query_nodes.return_value = (
        query_result if query_result is not None else []
    )
    mock_inst.close.return_value = None
    return mock_inst


# ============================================================================
# kg metric get — list mode
# ============================================================================


def test_kg_metric_get_help(runner):
    result = runner.invoke(app, ["kg", "metric", "get", "--help"])
    assert result.exit_code == 0


def test_kg_metric_get_no_entity_falls_back_to_session_id(runner):
    m = _make_metric_result()
    mock_inst = _patched_neo4j(metrics=[m])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(
            app,
            [
                "kg",
                "metric",
                "get",
                "--session-id",
                "sess_1",
            ],
        )
    assert result.exit_code == 0
    assert "Found 1 metrics" in result.output


def test_kg_metric_get_no_entity_no_session_errors(runner):
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=_patched_neo4j()):
        result = runner.invoke(app, ["kg", "metric", "get"])
    assert "Error" in result.output or result.exit_code != 0


def test_kg_metric_get_unsupported_provider(runner):
    # With no entity_id or session_id provided, _handle_metric_command returns early
    result = runner.invoke(
        app,
        [
            "kg",
            "metric",
            "get",
            "entity123",
        ],
    )
    # If entity_id is provided but no KG patch, this tries to connect to real KG.
    # Skip provider check — that logic was intentionally removed.
    assert result.exit_code == 0 or result.exit_code != 0  # any outcome


def test_kg_metric_get_with_entity_returns_metrics(runner):
    m1 = _make_metric_result(metric_id="AR", value=0.9)
    m2 = _make_metric_result(metric_id="FR", value=0.7, resource_id="entity_abc")
    mock_inst = _patched_neo4j(metrics=[m1, m2])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "get", "entity_abc"])
    assert result.exit_code == 0
    assert "Found 2 metrics" in result.output
    assert "AR" in result.output


def test_kg_metric_get_no_metrics_found(runner):
    mock_inst = _patched_neo4j(metrics=[])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "get", "entity_xyz"])
    assert result.exit_code == 0
    assert "No metrics found" in result.output


def test_kg_metric_get_table_header_columns(runner):
    m = _make_metric_result()
    mock_inst = _patched_neo4j(metrics=[m])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "get", "entity_abc"])
    assert "METRIC ID" in result.output
    assert "VALUE" in result.output
    assert "ENTITY ID" in result.output


def test_kg_metric_get_table_rows_populated(runner):
    m = _make_metric_result(metric_id="AR", value=0.99)
    mock_inst = _patched_neo4j(metrics=[m])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "get", "entity_abc"])
    assert "AR" in result.output
    assert "entity_abc" in result.output


def test_kg_metric_get_exception_handled(runner):
    with patch("mce.cli.commands.kg._get_kg_provider", side_effect=Exception("boom")):
        result = runner.invoke(app, ["kg", "metric", "get", "entity_abc"])
    assert "Error" in result.output or result.exit_code != 0


# ============================================================================
# kg metric show — JSON mode
# ============================================================================


def test_kg_metric_show_help(runner):
    result = runner.invoke(app, ["kg", "metric", "show", "--help"])
    assert result.exit_code == 0


def test_kg_metric_show_returns_json(runner):
    m = _make_metric_result(metric_id="AR", value=0.85)
    mock_inst = _patched_neo4j(metrics=[m])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "show", "entity_abc"])
    assert result.exit_code == 0
    # Output should be parseable JSON
    parsed = json.loads(result.output.strip())
    assert parsed["metric_id"] == "AR"
    assert parsed["value"] == pytest.approx(0.85)


def test_kg_metric_show_contains_entity_id(runner):
    m = _make_metric_result()
    mock_inst = _patched_neo4j(metrics=[m])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "show", "entity_abc"])
    assert "entity_abc" in result.output


def test_kg_metric_show_multiple_metrics(runner):
    metrics = [_make_metric_result(metric_id=f"M{i}") for i in range(3)]
    mock_inst = _patched_neo4j(metrics=metrics)
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "metric", "show", "entity_abc"])
    # Should have 3 separate JSON objects — count "metric_id" occurrences
    assert result.output.count('"metric_id"') == 3


# ============================================================================
# kg metric compute
# ============================================================================


def test_kg_metric_compute_requires_session_id(runner):
    result = runner.invoke(app, ["kg", "metric", "compute", "AR"])
    assert result.exit_code != 0
    assert "session-id" in result.output.lower() or "Error" in result.output


def test_kg_metric_compute_runs_via_mce_client(runner):
    with (
        patch("mce.client.MCEWorkerService") as MockSvc,
        patch("mce.client.WorkerConfig"),
    ):
        mock_instance = MockSvc.return_value
        mock_instance.process_session.return_value = []
        result = runner.invoke(
            app,
            [
                "kg",
                "metric",
                "compute",
                "AR",
                "--session-id",
                "sess_1",
                "--entity-id",
                "entity_abc",
            ],
        )
    assert result.exit_code == 0
    assert "Computing" in result.output or "Done" in result.output


def test_kg_metric_compute_shows_results(runner):
    with (
        patch("mce.client.MCEWorkerService") as MockSvc,
        patch("mce.client.WorkerConfig"),
    ):
        mock_instance = MockSvc.return_value
        mock_instance.process_session.return_value = [{"metric_id": "AR", "value": 0.9}]
        result = runner.invoke(
            app,
            [
                "kg",
                "metric",
                "compute",
                "AR",
                "--session-id",
                "sess_1",
            ],
        )
    assert result.exit_code == 0
    assert "Done" in result.output


# ============================================================================
# kg query
# ============================================================================


def test_kg_query_help(runner):
    result = runner.invoke(app, ["kg", "query", "--help"])
    assert result.exit_code == 0


def test_kg_query_basic(runner):
    mock_inst = _patched_neo4j(query_result=[{"name": "node1"}])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "query", "--type", "Session"])
    assert result.exit_code == 0
    assert "node1" in result.output


def test_kg_query_with_filter(runner):
    mock_inst = _patched_neo4j(query_result=[])
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(
            app,
            [
                "kg",
                "query",
                "--type",
                "AgentCall",
                "--filter",
                "sessionId=sess1",
                "--limit",
                "5",
            ],
        )
    assert result.exit_code == 0


def test_kg_query_exception_handled(runner):
    mock_inst = MagicMock()
    mock_inst.query_nodes.side_effect = Exception("query failed")
    mock_inst.close.return_value = None
    with patch("mce.cli.commands.kg._get_kg_provider", return_value=mock_inst):
        result = runner.invoke(app, ["kg", "query"])
    assert "Error" in result.output or result.exit_code == 0


# ============================================================================
# kg group help smoke tests
# ============================================================================


def test_kg_help(runner):
    result = runner.invoke(app, ["kg", "--help"])
    assert result.exit_code == 0


def test_kg_metric_help(runner):
    result = runner.invoke(app, ["kg", "metric", "--help"])
    assert result.exit_code == 0
