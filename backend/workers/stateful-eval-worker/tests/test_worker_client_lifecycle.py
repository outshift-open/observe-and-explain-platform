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
    monkeypatch.setitem(sys.modules, "oxp.client.local", SimpleNamespace(LocalClient=factory))
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
    factory.from_settings.assert_called_once_with(persist_metrics=persist_metrics)
    worker._close_db_handler()
    worker._close_db_handler()
    first.close.assert_called_once()
    assert worker._oxp_client is None
