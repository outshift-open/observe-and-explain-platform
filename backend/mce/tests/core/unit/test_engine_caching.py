#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.engine.caching — JsonFileCache, KnowledgeGraphCache, CacheManager."""

import json
import os
import pytest
from datetime import datetime
from unittest.mock import MagicMock
from mce.engine.caching import JsonFileCache, KnowledgeGraphCache, CacheManager
from mce.core.types import MetricResult


def _make_result(**kwargs):
    defaults = dict(
        metric_id="AR",
        resource_id="entity1",
        provider="Native",
        value=0.9,
        reasoning="test",
    )
    defaults.update(kwargs)
    r = MetricResult(**defaults)
    r.timestamp = datetime(2024, 1, 1)
    return r


# ============================================================================
# JsonFileCache
# ============================================================================


class TestJsonFileCache:
    def test_get_cache_miss(self, tmp_path):
        cache = JsonFileCache(str(tmp_path / "cache.json"))
        assert cache.get("e1", "AR") is None

    def test_store_and_get(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        cache = JsonFileCache(cache_file)
        r = _make_result()
        cache.store(r)
        result = cache.get("entity1", "AR")
        assert result is not None
        assert result["metric_id"] == "AR"

    def test_read_disabled_returns_none(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        cache = JsonFileCache(cache_file, read_enabled=False)
        r = _make_result()
        cache.store(r)
        assert cache.get("entity1", "AR") is None

    def test_write_disabled_does_not_persist(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        cache = JsonFileCache(cache_file, write_enabled=False)
        r = _make_result()
        cache.store(r)
        # File should NOT exist (write disabled)
        assert not os.path.exists(cache_file)

    def test_load_existing_file(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        data = {"entity1": {"AR": {"metric_id": "AR", "value": 0.5}}}
        with open(cache_file, "w") as f:
            json.dump(data, f)
        cache = JsonFileCache(cache_file)
        result = cache.get("entity1", "AR")
        assert result is not None
        assert result["value"] == 0.5

    def test_load_corrupt_file_graceful(self, tmp_path):
        cache_file = str(tmp_path / "cache.json")
        with open(cache_file, "w") as f:
            f.write("not valid json {{")
        cache = JsonFileCache(cache_file)
        # Should still work, just empty memory
        assert cache.get("x", "y") is None

    def test_save_error_logged(self, tmp_path):
        cache = JsonFileCache("/nonexistent/path/cache.json")
        r = _make_result()
        # Should not raise even if dir doesn't exist
        cache.store(r)


# ============================================================================
# KnowledgeGraphCache
# ============================================================================


class TestKnowledgeGraphCache:
    def test_read_disabled_returns_none(self):
        cache = KnowledgeGraphCache(MagicMock(), read_enabled=False)
        assert cache.get("e1", "AR") is None

    def test_no_provider_returns_none(self):
        cache = KnowledgeGraphCache(None)
        assert cache.get("e1", "AR") is None

    def test_provider_no_get_metric_result_returns_none(self):
        mock_prov = MagicMock(spec=[])  # no get_metric_result
        cache = KnowledgeGraphCache(mock_prov)
        assert cache.get("e1", "AR") is None

    def test_cache_hit(self):
        mock_prov = MagicMock()
        mock_result = MagicMock()
        mock_result.metric_id = "AR"
        mock_result.resource_id = "e1"
        mock_result.value = 0.7
        mock_result.provider = "neo4j"
        mock_result.reasoning = ""
        mock_result.metadata = {}
        mock_prov.get_metrics.return_value = [mock_result]
        cache = KnowledgeGraphCache(mock_prov)
        result = cache.get("e1", "AR")
        assert result["value"] == pytest.approx(0.7)

    def test_cache_miss_returns_none(self):
        mock_prov = MagicMock()
        mock_prov.get_metric_result.return_value = None
        cache = KnowledgeGraphCache(mock_prov)
        assert cache.get("e1", "AR") is None

    def test_provider_exception_returns_none(self):
        mock_prov = MagicMock()
        mock_prov.get_metric_result.side_effect = Exception("db error")
        cache = KnowledgeGraphCache(mock_prov)
        assert cache.get("e1", "AR") is None

    def test_store_is_noop(self):
        cache = KnowledgeGraphCache(MagicMock())
        r = _make_result()
        cache.store(r)  # Should not raise

    def test_store_skips_errored_results(self):
        mock_prov = MagicMock()
        cache = KnowledgeGraphCache(mock_prov)
        r = _make_result(error="boom")

        cache.store(r)
        cache.flush()

        mock_prov.save_metrics.assert_not_called()

    def test_flush_persists_only_successful_results(self):
        mock_prov = MagicMock()
        saved_on_flush: list[MetricResult] = []
        mock_prov.save_metrics.side_effect = lambda buf: saved_on_flush.extend(
            list(buf)
        )
        cache = KnowledgeGraphCache(mock_prov)

        ok = _make_result(metric_id="GoalSuccessRate")
        bad = _make_result(metric_id="Duration", error="missing duration")

        cache.store(ok)
        cache.store(bad)
        cache.flush()

        mock_prov.save_metrics.assert_called_once()
        assert [r.metric_id for r in saved_on_flush] == ["GoalSuccessRate"]


# ============================================================================
# CacheManager
# ============================================================================


class TestCacheManager:
    def test_get_returns_first_hit(self):
        b1 = MagicMock()
        b1.get_batch.return_value = {("e1", "AR"): {"metric_id": "AR"}}
        b2 = MagicMock()
        cm = CacheManager([b1, b2])
        result = cm.get("e1", "AR")
        assert result["metric_id"] == "AR"
        b2.get_batch.assert_not_called()

    def test_get_falls_through_to_second(self):
        b1 = MagicMock()
        b1.get_batch.return_value = {}
        b2 = MagicMock()
        b2.get_batch.return_value = {("e1", "AR"): {"metric_id": "AR"}}
        cm = CacheManager([b1, b2])
        result = cm.get("e1", "AR")
        assert result is not None

    def test_get_all_miss_returns_none(self):
        b1, b2 = MagicMock(), MagicMock()
        b1.get.return_value = None
        b2.get.return_value = None
        cm = CacheManager([b1, b2])
        assert cm.get("e1", "AR") is None

    def test_store_calls_all_backends(self):
        b1, b2 = MagicMock(), MagicMock()
        cm = CacheManager([b1, b2])
        r = _make_result()
        cm.store(r)
        b1.store.assert_called_once_with(r)
        b2.store.assert_called_once_with(r)

    def test_store_skips_virtual_metrics(self):
        b1 = MagicMock()
        cm = CacheManager([b1])
        r = _make_result(provider="virtual")
        cm.store(r)
        b1.store.assert_not_called()

    def test_is_virtual_metric(self):
        cm = CacheManager([])
        virtual_r = _make_result(provider="virtual")
        normal_r = _make_result(provider="Native")
        assert cm._is_virtual_metric(virtual_r) is True
        assert cm._is_virtual_metric(normal_r) is False
