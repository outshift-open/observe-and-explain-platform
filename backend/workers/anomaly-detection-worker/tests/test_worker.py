#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import pytest
from dem.anomaly import AnomalyDetectionSessions

from anomaly_detection_worker.worker import AnomalyDetectionInputMessage, AnomalyDetectionWorker


def test_anomaly_detection_worker_init(mocker):
    mocker.patch("worker_base.base_worker.get_neo4j_connector")
    worker = AnomalyDetectionWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        embedding_model="test-embedding-model",
        layers={"text": {"model_name": "isolation_forest"}},
        debug=True,
    )
    assert worker.name == "AnomalyDetectionWorker"
    assert worker.embedding_model == "test-embedding-model"


@pytest.mark.asyncio
async def test_handle_message_argo_mode(mocker):
    mocker.patch("worker_base.base_worker.get_neo4j_connector")
    mock_wrapper = mocker.patch("anomaly_detection_worker.worker.AnomalyDetectionWrapper")
    mock_wrapper_instance = mock_wrapper.return_value
    mock_wrapper_instance.process_group.return_value = [
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

    worker = AnomalyDetectionWorker(
        rabbitmq_url="amqp://guest:guest@localhost/",
        input_queue="input_queue",
        embedding_model="test-model",
    )

    msg = AnomalyDetectionInputMessage(
        session_id="s1",
        group_id="group1",
        group_hash="hash123",
        sessions=[
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
        ],
    )

    result = await worker.handle_message(msg)

    assert result is True
    mock_wrapper_instance.process_group.assert_called_once()
    assert len(worker.output_messages) == 1
    output = worker.output_messages[0]
    assert output.group_id == "group1"
    assert len(output.anomalies) == 1
    assert output.anomalies[0]["layer"] == "text"
