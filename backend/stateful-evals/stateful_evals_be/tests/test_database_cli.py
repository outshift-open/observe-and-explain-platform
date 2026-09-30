#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Database CLI boundaries use library calls, not API-server requests."""

import json
from contextlib import nullcontext
from unittest.mock import Mock

from stateful_evals_be.scripts import push_metrics_to_oxp as push
from stateful_evals_be.scripts import run_session_eval


def test_session_cli_writes_legacy_metric_via_library(monkeypatch):
    client = Mock()
    client.write_session_metrics.return_value = {"written": 1, "errors": []}
    factory = Mock(return_value=nullcontext(client))
    monkeypatch.setattr("stateful_evals_be.integrations.oxp.local_api_client", factory)
    run_session_eval._push_trajectory_score("session", 0)
    factory.assert_called_once_with(persist_metrics=True)
    client.write_session_metrics.assert_called_once_with(
        "session",
        [
            {
                "name": "trajectory_score",
                "value": 0,
                "provider": "stateful_evals",
                "metric_id": None,
                "source": "StatefulEval",
                "reasoning": None,
            }
        ],
    )


def test_saved_metric_cli_writes_through_client(tmp_path):
    path = tmp_path / "session_metrics.json"
    records = [
        {
            "aggregation_level": "session",
            "session_id": ["session"],
            "metric_name": "trajectory_score",
            "value": 1,
            "reasoning": "Complete.",
        },
        {
            "aggregation_level": "span",
            "session_id": ["session"],
            "span_id": ["span"],
            "metric_name": "Groundedness",
            "value": 0,
            "reasoning": "Unsupported.",
        },
    ]
    path.write_text(json.dumps(records))
    client = Mock()
    client.write_session_metrics.return_value = {"written": 1, "errors": []}
    client.write_span_metrics.return_value = {"written": 1, "errors": []}
    assert push.push_file(path, client) == {
        "session_posted": 1,
        "span_posted": 1,
        "skipped": 0,
        "errors": 0,
    }
    sid, metrics = client.write_session_metrics.call_args.args
    assert sid == "session"
    assert metrics[0]["value"] == 1
    assert metrics[0]["reasoning"] == "Complete."
    sid, span_id, span_metrics = client.write_span_metrics.call_args.args
    assert (sid, span_id) == ("session", "span")
    assert span_metrics[0]["reasoning"] == "Unsupported."
    assert span_metrics[0]["metric_id"] == metrics[0]["metric_id"]
    client.close.assert_not_called()

    client.reset_mock()
    assert push.push_file(path, client, dry_run=True)["session_posted"] == 1
    client.write_session_metrics.assert_not_called()
    client.write_span_metrics.assert_not_called()

    client.write_session_metrics.side_effect = RuntimeError("unavailable")
    assert push.push_file(path, client, session_only=True)["errors"] == 1
