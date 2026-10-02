#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from stateful_eval_worker.worker import StatefulEvalWorker


@pytest.mark.parametrize("persist_metrics", [False, True])
def test_worker_uses_api_factory_and_closes_owned_client(monkeypatch, rabbit_url, persist_metrics):
    factory = Mock()
    shared = Mock()
    monkeypatch.setitem(sys.modules, "oxp.client.local", SimpleNamespace(LocalClient=factory))
    monkeypatch.setitem(sys.modules, "oxp.dependencies", SimpleNamespace(get_neo4j_connector=Mock(return_value=shared)))
    worker = StatefulEvalWorker(
        rabbit_url=rabbit_url,
        input_queue="test",
        llm_api_key="test-only",
        llm_model_name="test-model",
        llm_base_model_url="https://example.invalid/v1",
    )
    worker.push_metrics = persist_metrics
    first = worker._get_oxp_client()
    assert worker._get_oxp_client() is first
    factory.from_settings.assert_called_once_with(
        persist_metrics=persist_metrics, neo4j=shared if persist_metrics else None
    )
    worker._close_db_handler()
    worker._close_db_handler()
    first.close.assert_called_once()
    assert worker._oxp_client is None
