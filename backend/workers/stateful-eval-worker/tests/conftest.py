#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import pytest
from worker_base.queue_message import SessionDetailMessage


@pytest.fixture
def rabbit_url():
    return "amqp://guest:guest@localhost/"


@pytest.fixture
def llm_params():
    return {
        "llm_api_key": "test-api-key",
        "llm_model_name": "gpt-4o",
        "llm_base_model_url": "https://api.openai.com/v1",
    }


@pytest.fixture
def session_message():
    return SessionDetailMessage(
        job_id="job-abc",
        session_id="session-xyz",
        workflow_id="workflow-123",
        metrics=None,
        input_content="user question",
        input_embedding=[0.1, 0.2],
        output_content="agent answer",
        output_embedding=[0.3, 0.4],
        execution_graph={"nodes": ["a"], "edges": []},
    )


def make_failure_detail(
    metric="Groundedness",
    fatality_score=1.0,
    reasoning="bad",
    span_index=2,
    entity_name="my_tool",
):
    return SimpleNamespace(
        metric=metric,
        fatality_score=fatality_score,
        reasoning=reasoning,
        span_index=span_index,
        entity_name=entity_name,
    )


def make_session_result(
    session_id="session-xyz",
    error=None,
    trajectory_score=1,
    trajectory_reasoning='{"total_fatal": 0, "fatal_failures": []}',
    unsatisfied_intents=0,
    span_metric_results=None,
    fatal_failures=None,
):
    return SimpleNamespace(
        session_id=session_id,
        error=error,
        trajectory_score=trajectory_score,
        trajectory_reasoning=trajectory_reasoning,
        unsatisfied_intents=unsatisfied_intents,
        span_metric_results=span_metric_results or [],
        fatal_failures=fatal_failures or [],
    )
