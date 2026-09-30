#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
import pytest
from mce.client.adapters.json_provider import JsonDataProvider
from mce.core.metadata import MetricRequirements


def test_json_provider_file_not_found():
    with pytest.raises(FileNotFoundError):
        JsonDataProvider("nonexistent_file.json")


def test_json_provider_list_format(tmp_path):
    f = tmp_path / "data.json"
    data = [{"id": "sess-1", "val": 1}, {"session_id": "sess-2", "val": 2}]
    f.write_text(json.dumps(data))

    provider = JsonDataProvider(str(f))
    assert "sess-1" in provider.list_session_ids()
    assert "sess-2" in provider.list_session_ids()
    result = provider.fetch("sess-1", MetricRequirements())
    # fetch() injects a "session" key for session-level metrics (e.g. Duration)
    assert result["id"] == "sess-1"
    assert result["val"] == 1
    assert "session" in result
    assert result["session"]["id"] == "sess-1"


def test_json_provider_dict_format(tmp_path):
    f = tmp_path / "data_dict.json"
    data = {"sess-A": {"id": "sess-A"}}
    f.write_text(json.dumps(data))

    provider = JsonDataProvider(str(f))
    result = provider.fetch("sess-A", MetricRequirements())
    # fetch() injects a "session" key for session-level metrics (e.g. Duration)
    assert result["id"] == "sess-A"
    assert "session" in result
    assert result["session"]["id"] == "sess-A"


def test_json_provider_invalid_format(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text('"just a string"')

    with pytest.raises(ValueError):
        JsonDataProvider(str(f))


def test_json_provider_lookup_error(tmp_path):
    f = tmp_path / "empty.json"
    f.write_text("[]")

    provider = JsonDataProvider(str(f))
    with pytest.raises(LookupError):
        provider.fetch("missing", MetricRequirements())
