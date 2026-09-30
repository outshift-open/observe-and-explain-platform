#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E402

import sys
from unittest.mock import MagicMock

# Pre-mock deepeval before any mce imports to avoid ValueError on deepeval.__spec__
for _m in [
    "deepeval",
    "deepeval.metrics",
    "deepeval.test_case",
    "deepeval.models",
    "deepeval.telemetry",
]:
    _existing = sys.modules.get(_m)
    if _existing is None or (
        isinstance(_existing, MagicMock)
        and getattr(_existing, "__spec__", "unset") is not None
    ):
        _mock = MagicMock()
        _mock.__spec__ = None
        sys.modules[_m] = _mock

import pytest
from click.testing import CliRunner
from unittest.mock import MagicMock, patch
from mce.cli.main import app
from mce.core.types import MetricResult
from mce.core.metadata import MetricScope


@pytest.fixture
def runner():
    return CliRunner()


def test_main_app_help(runner):
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Metrics Computation Engine" in result.output


@patch("mce.cli.helpers.setup_engine")
@patch("mce.cli.helpers.setup_cache_manager")
@patch("mce.cli.helpers.setup_data_provider")
def test_main_compute(mock_setup_provider, mock_setup_cache, mock_setup_engine, runner):
    # Setup mock provider
    mock_provider = MagicMock()
    mock_setup_provider.return_value = mock_provider

    # Mock result with required fields
    res1 = MetricResult(
        metric_id="ToolError",
        resource_id="span_123",
        provider="Native",
        value=0.5,
        reasoning="Test reason",
        metadata={"scope": MetricScope.SPAN.value},
    )
    mock_engine_instance = MagicMock()
    mock_engine_instance.compute_session.return_value = [res1]
    mock_setup_engine.return_value = mock_engine_instance
    mock_setup_cache.return_value = MagicMock()

    # Invoke with --all flag to skip metric selection error
    result = runner.invoke(app, ["compute", "--session-id", "s1", "--all"])

    # Verify
    assert result.exit_code == 0, f"Exit code non-zero. Output:\n{result.output}"
    mock_setup_provider.assert_called_once()
    _, kwargs = mock_setup_cache.call_args
    assert kwargs["no_cache_read"] is True
    assert kwargs["no_cache_write"] is True
    mock_engine_instance.compute_session.assert_called_once()


@patch("mce.cli.helpers.setup_data_provider", return_value=None)
def test_main_compute_no_provider(mock_setup_provider, runner):
    result = runner.invoke(app, ["compute", "--session-id", "s1"])
    assert result.exit_code == 0
    assert "Failed to initialize data provider" in result.output


@patch("mce.cli.helpers.setup_data_provider")
@patch("mce.client.config.MCEClientConfig.from_env")
@patch("mce.client.worker.MCEWorkerService")
def test_main_compute_workflow_path_uses_worker_service(
    mock_worker_service, mock_from_env, mock_setup_provider, runner, tmp_path
):
    cfg = tmp_path / "worker_config.yaml"
    cfg.write_text("metrics:\n  Session:\n    - AnswerRelevancy\n")

    mock_svc = MagicMock()
    mock_svc.config.path = cfg
    mock_svc.process_session.return_value = [
        {
            "metric_id": "AnswerRelevancy",
            "value": 0.8,
            "reasoning": "ok",
        }
    ]
    mock_worker_service.return_value = mock_svc
    mock_from_env.return_value = MagicMock()

    result = runner.invoke(
        app,
        [
            "compute",
            "--session-id",
            "s1",
            "--workflow-path",
            "--worker-config",
            str(cfg),
        ],
    )

    assert result.exit_code == 0, f"Exit code non-zero. Output:\n{result.output}"
    mock_setup_provider.assert_not_called()
    mock_from_env.assert_called_once_with()
    mock_worker_service.assert_called_once_with(
        config_path=cfg,
        client_config=mock_from_env.return_value,
        cache_read=False,
        cache_write=False,
    )
    mock_svc.process_session.assert_called_once_with("s1")


@patch("mce.client.config.MCEClientConfig.from_env")
@patch("mce.client.worker.MCEWorkerService")
def test_main_compute_workflow_path_honors_cache_flags(
    mock_worker_service, mock_from_env, runner, tmp_path
):
    cfg = tmp_path / "worker_config.yaml"
    cfg.write_text("metrics:\n  Session:\n    - AnswerRelevancy\n")

    mock_svc = MagicMock()
    mock_svc.config.path = cfg
    mock_svc.process_session.return_value = []
    mock_worker_service.return_value = mock_svc
    mock_from_env.return_value = MagicMock()

    result = runner.invoke(
        app,
        [
            "compute",
            "--session-id",
            "s1",
            "--workflow-path",
            "--worker-config",
            str(cfg),
            "--cache-read",
            "--cache-write",
        ],
    )

    assert result.exit_code == 0, f"Exit code non-zero. Output:\n{result.output}"
    mock_worker_service.assert_called_once_with(
        config_path=cfg,
        client_config=mock_from_env.return_value,
        cache_read=True,
        cache_write=True,
    )


@patch("mce.cli.commands.compute.logger")
@patch("mce.client.worker.MCEWorkerService")
def test_main_compute_workflow_path_logs_exception(
    mock_worker_service, mock_logger, runner, tmp_path
):
    cfg = tmp_path / "worker_config.yaml"
    cfg.write_text("metrics:\n  Session:\n    - AnswerRelevancy\n")

    mock_svc = MagicMock()
    mock_svc.config.path = cfg
    mock_svc.process_session.side_effect = RuntimeError("boom")
    mock_worker_service.return_value = mock_svc

    result = runner.invoke(
        app,
        [
            "compute",
            "--session-id",
            "s1",
            "--workflow-path",
            "--worker-config",
            str(cfg),
        ],
    )

    assert result.exit_code == 0
    assert "see logs for traceback" in result.output
    mock_logger.exception.assert_called_once()


def test_list_metrics(runner):
    result = runner.invoke(app, ["list-metrics"])
    assert result.exit_code == 0
    assert "METRIC NAME" in result.output
    # Check for a known metric (PascalCase IDs)
    assert "ToolError" in result.output


def test_show_metric(runner):
    # Test valid metric (PascalCase ID)
    result = runner.invoke(app, ["show-metric", "ToolErrorRate"])
    assert result.exit_code == 0
    assert "ToolErrorRate" in result.output
    assert "Scope" in result.output

    # Test invalid metric
    result = runner.invoke(app, ["show-metric", "nonexistent_metric"])
    assert result.exit_code == 0
    assert "Metric 'nonexistent_metric' not found" in result.output
