#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest
from dem.anomaly import AnomalyDetectionSessions
from worker_base.queue_message import SessionGroupMessage

from analysis_worker.worker import AnalysisWorker

_SESSIONS = [
    {
        "session_id": "s1",
        "metrics": {"Cost": 1.0},
        "input_content": "test",
        "input_embedding": [0.1, 0.2],
        "output_content": "result",
        "output_embedding": [0.3, 0.4],
        "execution_graph": {},
    },
    {
        "session_id": "s2",
        "metrics": {"Cost": 1.1},
        "input_content": "test2",
        "input_embedding": [0.1, 0.2],
        "output_content": "result2",
        "output_embedding": [0.3, 0.4],
        "execution_graph": {},
    },
    {
        "session_id": "s3",
        "metrics": {"Cost": 5.0},
        "input_content": "test3",
        "input_embedding": [0.9, 0.8],
        "output_content": "result3",
        "output_embedding": [0.7, 0.6],
        "execution_graph": {},
    },
]


@pytest.fixture(autouse=True)
def _mock_api_neo4j_connector(mocker):
    mock_connector = mocker.MagicMock()
    mocker.patch("worker_base.base_worker.get_neo4j_connector", return_value=mock_connector)
    return mock_connector


def test_analysis_worker_init(mocker):
    worker = AnalysisWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        embedding_model="test-embedding-model",
        n_workers=5,
        debug=True,
    )
    assert worker.name == "AnalysisWorker"
    assert worker.embedding_model == "test-embedding-model"


@pytest.mark.asyncio
async def test_handle_message_argo_mode(mocker):
    mock_anomaly = mocker.patch("analysis_worker.worker.AnomalyDetectionWrapper")
    mock_consistency = mocker.patch("analysis_worker.worker.ConsistencyWrapper")
    mock_normal = mocker.patch("analysis_worker.worker.NormalBehaviourWrapper")

    mock_anomaly.return_value.process_group.return_value = [
        AnomalyDetectionSessions(
            layer="text",
            reason="test anomaly",
            inlier_sessions=["s1", "s2"],
            outlier_sessions=["s3"],
            scores=[0.1, 0.2, 0.9],
            threshold=0.5,
            metadata={"model_name": "isolation_forest"},
        )
    ]
    mock_anomaly.return_value.ingest_anomaly_report.return_value = True
    mock_consistency.return_value.process_group.return_value = []
    mock_normal.return_value.process_group.return_value = []

    worker = AnalysisWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        embedding_model="test-model",
        n_workers=3,
    )

    mock_db = mocker.MagicMock()
    mock_db.analysis_pre_check.return_value = True
    worker.db_handler = mock_db

    msg = SessionGroupMessage(
        session_id="s1",
        group_id="group1",
        group_hash="hash123",
        sessions=_SESSIONS,
    )

    result = await worker.handle_message(msg)

    assert result is True
    assert len(worker.output_messages) == 1
    output = worker.output_messages[0]
    assert output.group_id == "group1"
    assert len(output.anomalies) == 1
    assert output.anomalies[0]["layer"] == "text"


@pytest.mark.asyncio
async def test_handle_message_no_db_without_sessions(mocker):
    """Worker should return False when no sessions and no db_handler."""
    worker = AnalysisWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        embedding_model="test-model",
    )
    worker.db_handler = None

    msg = SessionGroupMessage(
        session_id="s1",
        group_id="group1",
        group_hash="hash123",
        sessions=[],
    )

    result = await worker.handle_message(msg)
    assert result is False


@pytest.mark.asyncio
async def test_handle_message_no_embedding_model_without_sessions(mocker):
    """Worker should return False when no sessions and no embedding_model."""
    worker = AnalysisWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        embedding_model="",
    )

    msg = SessionGroupMessage(
        session_id="s1",
        group_id="group1",
        group_hash="hash123",
        sessions=[],
    )

    result = await worker.handle_message(msg)
    assert result is False


def test_session_group_message_defaults_sessions_to_empty_list():
    msg = SessionGroupMessage(session_id="s1", group_id="group1", group_hash="hash123", sessions=None)

    assert msg.sessions == []
