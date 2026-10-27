#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""The worker's config file is taken from ``--config-file`` or ``COGNITIVE_FAILURE_CONFIG_PATH``."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

from cognitive_failure_worker import cli


@pytest.fixture
def build_worker(mocker, monkeypatch):
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    monkeypatch.delenv("COGNITIVE_FAILURE_CONFIG_PATH", raising=False)
    worker = MagicMock()
    worker.run = AsyncMock()
    return mocker.patch.object(cli, "_build_worker", return_value=worker)


def test_the_config_file_flag_reaches_the_worker(build_worker):
    result = CliRunner().invoke(cli.main, ["--config-file", "/oxp/cognitive_failure_config.yaml"])

    assert result.exit_code == 0, result.output
    assert build_worker.call_args.kwargs["config_path"] == "/oxp/cognitive_failure_config.yaml"


def test_the_config_path_falls_back_to_the_environment(build_worker, monkeypatch):
    monkeypatch.setenv("COGNITIVE_FAILURE_CONFIG_PATH", "/from/env.yaml")

    result = CliRunner().invoke(cli.main, [])

    assert result.exit_code == 0, result.output
    assert build_worker.call_args.kwargs["config_path"] == "/from/env.yaml"


def test_the_flag_wins_over_the_environment(build_worker, monkeypatch):
    monkeypatch.setenv("COGNITIVE_FAILURE_CONFIG_PATH", "/from/env.yaml")

    CliRunner().invoke(cli.main, ["--config-file", "/from/flag.yaml"])

    assert build_worker.call_args.kwargs["config_path"] == "/from/flag.yaml"


def test_no_config_means_no_config_path(build_worker):
    CliRunner().invoke(cli.main, [])

    assert build_worker.call_args.kwargs["config_path"] is None
