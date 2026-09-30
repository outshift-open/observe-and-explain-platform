#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
from click.testing import CliRunner
from unittest.mock import patch
import json

from mce.legacy.cli.legacy import legacy_cli
from mce.core.types import MetricResult
from mce.core.metadata import MetricScope


@pytest.fixture
def runner():
    return CliRunner()


def test_list_metrics(runner):
    result = runner.invoke(legacy_cli, ["list-metrics"])
    assert result.exit_code == 0
    assert "Available metrics (Simulated Legacy View):" in result.output
    assert "ToolError" in result.output


@patch("mce.engine.engine.MetricEngine")
@patch("mce.legacy.cli.legacy._get_kg_provider")
def test_compute_cmd_success(MockProvider, MockEngine, runner, tmp_path):
    config_data = {
        "session_id": "test_session_1",
        "metrics": ["ToolError", "ResponseCompleteness"],
    }
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))

    mock_engine_instance = MockEngine.return_value
    res1 = MetricResult(
        metric_id="ToolError",
        metric_class="ToolError",
        resource_id="span_123",
        provider="Native",
        value=0.5,
        reasoning="Test reason",
        metadata={"scope": MetricScope.SPAN.value},
    )
    mock_engine_instance.compute_session.return_value = [res1]

    result = runner.invoke(legacy_cli, ["compute", str(config_file)])

    assert result.exit_code == 0, f"Output: {result.output}"
    assert "Running V1 Legacy Compute" in result.output
    assert '"metric_name": "ToolError"' in result.output
    assert '"value": 0.5' in result.output
    mock_engine_instance.compute_session.assert_called_with("test_session_1")


@patch("mce.engine.engine.MetricEngine")
@patch("mce.legacy.cli.legacy._get_kg_provider")
def test_compute_cmd_with_unsupported_metric(
    MockProvider, MockEngine, runner, tmp_path
):
    config_data = {"session_id": "s1", "metrics": ["UnknownMetric"]}
    config_file = tmp_path / "bad_config.json"
    config_file.write_text(json.dumps(config_data))

    MockEngine.return_value.compute_session.return_value = []

    result = runner.invoke(legacy_cli, ["compute", str(config_file)])

    assert result.exit_code == 0  # Warning, not error
    assert "Warning: Metric 'UnknownMetric' not found" in result.output
