#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from stateful_eval_worker.worker import StatefulEvalWorker


def test_worker_uses_the_shared_neo4j_connector(monkeypatch, rabbit_url):
    shared = Mock()
    monkeypatch.setitem(sys.modules, "oxp.dependencies", SimpleNamespace(get_neo4j_connector=Mock(return_value=shared)))
    worker = StatefulEvalWorker(
        rabbit_url=rabbit_url,
        input_queue="test",
        llm_api_key="test-only",
        llm_model_name="test-model",
        llm_base_model_url="https://example.invalid/v1",
    )
    assert worker._get_kg() is shared
    assert worker._get_kg() is shared
    # the base worker owns the connector; this worker must not close it
    worker._close_db_handler()
    shared.close.assert_not_called()
