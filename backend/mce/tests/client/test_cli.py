#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.client.cli — CLI commands."""

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from mce.client.cli import app


_MINIMAL_YAML = {
    "engine": {"max_workers": 2, "execution_strategy": "thread"},
    "metrics": {
        "session": ["AnswerRelevancy"],
        "llm_call": ["Duration"],
        "tool_call": ["ToolError"],
    },
}

_INVALID_YAML = {
    "engine": {"max_workers": 999, "execution_strategy": "bad"},
}


@pytest.fixture()
def runner():
    return CliRunner()


@pytest.fixture()
def valid_config(tmp_path) -> Path:
    p = tmp_path / "worker_config.yaml"
    p.write_text(yaml.dump(_MINIMAL_YAML))
    return p


@pytest.fixture()
def invalid_config(tmp_path) -> Path:
    p = tmp_path / "bad_config.yaml"
    p.write_text(yaml.dump(_INVALID_YAML))
    return p


# ---------------------------------------------------------------------------
# validate-config
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_valid_config_exits_zero(self, runner, valid_config):
        result = runner.invoke(app, ["validate-config", str(valid_config)])
        assert result.exit_code == 0

    def test_valid_config_prints_summary(self, runner, valid_config):
        result = runner.invoke(app, ["validate-config", str(valid_config)])
        assert "Config valid" in result.output
        assert "strategy=thread" in result.output

    def test_valid_config_shows_metric_counts(self, runner, valid_config):
        result = runner.invoke(app, ["validate-config", str(valid_config)])
        assert "session=1" in result.output
        assert "llm_call=1" in result.output
        assert "tool_call=1" in result.output

    def test_invalid_config_exits_one(self, runner, invalid_config):
        result = runner.invoke(app, ["validate-config", str(invalid_config)])
        assert result.exit_code == 1

    def test_invalid_config_prints_error(self, runner, invalid_config):
        result = runner.invoke(app, ["validate-config", str(invalid_config)])
        assert "✗" in result.output or "Invalid" in result.output

    def test_schema_flag_prints_schema_path(self, runner, valid_config):
        result = runner.invoke(app, ["validate-config", str(valid_config), "--schema"])
        assert "Schema:" in result.output
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# show-config
# ---------------------------------------------------------------------------


class TestShowConfig:
    def test_yaml_format_default(self, runner, valid_config):
        result = runner.invoke(app, ["show-config", str(valid_config)])
        assert result.exit_code == 0
        parsed = yaml.safe_load(result.output)
        assert parsed["engine"]["max_workers"] == 2

    def test_json_format(self, runner, valid_config):
        result = runner.invoke(
            app, ["show-config", str(valid_config), "--format", "json"]
        )
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["engine"]["execution_strategy"] == "thread"

    def test_invalid_config_exits_one(self, runner, invalid_config):
        result = runner.invoke(app, ["show-config", str(invalid_config)])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# show-schema
# ---------------------------------------------------------------------------


class TestShowSchema:
    def test_prints_schema_path(self, runner):
        result = runner.invoke(app, ["show-schema"])
        assert result.exit_code == 0
        assert "worker_config.schema.yaml" in result.output

    def test_schema_path_exists(self, runner):
        result = runner.invoke(app, ["show-schema"])
        schema_path = Path(result.output.strip())
        assert schema_path.exists(), f"Schema file not found: {schema_path}"
