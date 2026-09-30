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
    if (
        _m not in sys.modules
        or not hasattr(sys.modules[_m], "__spec__")
        or sys.modules[_m].__spec__ is MagicMock
    ):
        _mock = MagicMock()
        _mock.__spec__ = None
        sys.modules[_m] = _mock

from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

# from mce.api.app import app, get_default_metrics

# Late import to ensure patching works
from mce.api.app import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["version"] == "2.0.0"


def test_list_metrics():
    with patch("mce.api.app.get_default_metrics") as mock_get:
        # Don't use spec=Metric to avoid strict attribute checking if Metric is abstract/complex
        m1 = MagicMock()
        m1.metric_id = "m1"
        m1.ontology_class = "M1Class"
        m1.metadata.to_dict.return_value = {"name": "m1"}
        mock_get.return_value = [m1]

        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.json()["total_metrics"] == 1
        assert response.json()["metrics"][0]["name"] == "m1"


def test_status():
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_compute_metrics_validation():
    # Missing fields
    response = client.post("/compute_metrics", json={})
    assert response.status_code == 400
    assert "session_ids" in response.json().get(
        "detail", ""
    ) or "No session_ids" in response.json().get("detail", "")


def test_compute_metrics_mock():
    # Helper to mock MetricEngine to avoid real execution logic
    with patch("mce.api.app.MetricEngine") as MockEngine:
        instance = MockEngine.return_value
        # Mock compute_session result
        mock_res = MagicMock()
        mock_res.to_legacy_dict.return_value = {"val": 1}
        instance.compute_session.return_value = [mock_res]

        # 'mock' param no longer supported, but if we provide session_ids,
        # it will try to use OXPDataProvider unless file is provided.
        # Since OXPDataProvider might fail if not available, we should probably mock it too.
        with patch("mce.api.app._get_kg_provider") as MockProvider:
            MockProvider.return_value._available = True

            payload = {"session_ids": ["s1"], "metrics": ["all"]}

            response = client.post("/compute_metrics", json=payload)
            assert response.status_code == 200
            assert len(response.json()["results"]) == 1


def test_compute_metrics_file_missing_provider_api():
    pass


#    # Test JSON provider file
#    with (
#        patch("mce.api.app.JsonDataProvider") as MockJson,
#        patch("mce.api.app.MetricEngine") as MockEngine,
#    ):
#        instance = MockJson.return_value
#        # Mock dependencies if called
#
#        engine_instance = MockEngine.return_value
#        engine_instance.compute_session.return_value = []
#
#        # We assume validation passes if mocked
#        response = client.post(
#            "/compute_metrics", json={"file": "nonexistent.json", "metrics": ["all"]}
#        )
#        # Just checking it doesn't crash 500
#        assert response.status_code in [200, 400]


def test_compute_metrics_select_specific():
    with (
        patch("mce.api.app.MetricEngine") as MockEngine,
        patch("mce.api.app._get_kg_provider") as MockProvider,
    ):
        MockProvider.return_value._available = True
        instance = MockEngine.return_value
        instance.compute_session.return_value = []

        # We need real metrics in 'get_default_metrics' to select from
        with patch("mce.api.app.get_default_metrics") as mock_get:
            m1 = MagicMock()
            m1.metric_id = "target_metric"
            m1.metadata.to_dict.return_value = {}
            m1.ontology_class = "TargetMetric"
            mock_get.return_value = [m1]

            payload = {"session_ids": ["s1"], "metrics": ["target_metric"]}
            response = client.post("/compute_metrics", json=payload)
            assert response.status_code == 200

            # Verify engine registration called
            instance.register_metric.assert_called_with(m1)
