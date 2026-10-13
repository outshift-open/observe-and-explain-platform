#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace

import pytest
from worker_base.queue_message import BaseQueueMessage

from stateful_eval_worker import queues
from stateful_eval_worker.worker import StatefulEvalWorker

from conftest import make_failure_detail, make_session_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fake_to_thread(fn, *args, **kwargs):
    """Drop-in for asyncio.to_thread that calls fn synchronously."""
    return fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def no_external_services(mocker):
    kg = mocker.Mock(spec=["execute", "execute_command", "ensure_connected"])
    mocker.patch.object(StatefulEvalWorker, "_get_kg", return_value=kg)
    mocker.patch("oxp.client.dal.get_session_trajectory", return_value=TRAJECTORY)
    return kg


TRAJECTORY = {"session_id": "session-xyz", "app_name": "app", "steps": [{"transition_id": "transition:1"}]}


def _make_worker(rabbit_url, **kwargs):
    defaults = dict(
        input_queue="test_input",
        llm_api_key="key",
        llm_model_name="gpt-4o",
        llm_base_model_url="https://api.openai.com/v1",
    )
    defaults.update(kwargs)
    return StatefulEvalWorker(rabbit_url=rabbit_url, **defaults)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------


def test_worker_name(rabbit_url):
    worker = _make_worker(rabbit_url)
    assert worker.name == "StatefulEvalWorker"


def test_worker_input_message_class(rabbit_url):
    worker = _make_worker(rabbit_url)
    assert worker.input_message_class is BaseQueueMessage


def test_worker_stores_explicit_params(rabbit_url):
    worker = _make_worker(
        rabbit_url,
        llm_api_key="my-key",
        llm_model_name="gpt-4-turbo",
        llm_base_model_url="https://custom.openai.com/v1",
    )

    assert worker.llm_api_key == "my-key"
    assert worker.llm_model_name == "gpt-4-turbo"
    assert worker.llm_base_model_url == "https://custom.openai.com/v1"


def test_worker_default_params(rabbit_url, monkeypatch):
    # Clear relevant env vars so we exercise the code defaults.
    for var in ("OPENAI_API_KEY", "LLM_MODEL_NAME", "LLM_BASE_MODEL_URL_MCE"):
        monkeypatch.delenv(var, raising=False)

    worker = StatefulEvalWorker(
        rabbit_url=rabbit_url,
        input_queue="test_input",
    )

    assert worker.llm_api_key == ""
    assert worker.llm_model_name == "gpt-4o"
    assert worker.llm_base_model_url == "https://api.openai.com/v1"


def test_worker_reads_llm_params_from_env(rabbit_url, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("LLM_MODEL_NAME", "gpt-env-model")
    monkeypatch.setenv("LLM_BASE_MODEL_URL_MCE", "https://env.openai.com/v1")

    worker = StatefulEvalWorker(
        rabbit_url=rabbit_url,
        input_queue="test_input",
    )

    assert worker.llm_api_key == "env-key"
    assert worker.llm_model_name == "gpt-env-model"
    assert worker.llm_base_model_url == "https://env.openai.com/v1"


def test_worker_explicit_params_override_env(rabbit_url, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("LLM_MODEL_NAME", "env-model")

    worker = _make_worker(
        rabbit_url,
        llm_api_key="explicit-key",
        llm_model_name="explicit-model",
    )

    assert worker.llm_api_key == "explicit-key"
    assert worker.llm_model_name == "explicit-model"


def test_worker_sampling_env_vars(rabbit_url, monkeypatch):
    monkeypatch.setenv("SAMPLING_STRATEGY", "tail_weighted")
    monkeypatch.setenv("SAMPLING_EARLY_RATE", "0.10")
    monkeypatch.setenv("SAMPLING_MID_RATE", "0.50")

    worker = _make_worker(rabbit_url)

    assert worker.sampling_strategy == "tail_weighted"
    assert worker.sampling_early_rate == pytest.approx(0.10)
    assert worker.sampling_mid_rate == pytest.approx(0.50)


# ---------------------------------------------------------------------------
# Queue constant
# ---------------------------------------------------------------------------


def test_queue_constant_value():
    assert queues.NEW_SESSION_TO_STATEFUL_EVAL_Q == "new_session_to_stateful_eval"


# ---------------------------------------------------------------------------
# handle_message — processor is mocked; asyncio.to_thread runs synchronously
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_message_returns_true_on_success(rabbit_url, session_message, mocker):
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    result = await worker.handle_message(session_message)

    assert result is True


@pytest.mark.asyncio
async def test_handle_message_produces_one_output_message(rabbit_url, session_message, mocker):
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)

    assert len(worker.output_messages) == 1
    assert isinstance(worker.output_messages[0], BaseQueueMessage)


@pytest.mark.asyncio
async def test_handle_message_output_preserves_input_fields(rabbit_url, session_message, mocker):
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)

    out = worker.output_messages[0]
    assert out.job_id == session_message.job_id
    assert out.session_id == session_message.session_id
    assert out.workflow_id == session_message.workflow_id


@pytest.mark.asyncio
async def test_handle_message_evaluates_the_kg_trajectory(rabbit_url, session_message, mocker, no_external_services):
    fake_result = make_session_result()
    get_trajectory = mocker.patch("oxp.client.dal.get_session_trajectory", return_value=TRAJECTORY)

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)

    get_trajectory.assert_called_once_with(no_external_services, session_message.session_id)
    mock_processor.evaluate_trajectory.assert_called_once_with(TRAJECTORY)
    mock_processor.evaluate_spans.assert_not_called()
    mock_processor.close.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_builds_processor_once_per_message(rabbit_url, session_message, mocker):
    """A fresh processor is created for each handle_message call."""
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mock_build = mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)
    await worker.handle_message(session_message)

    assert mock_build.call_count == 2


@pytest.mark.asyncio
async def test_handle_message_with_error_result_still_returns_true(rabbit_url, session_message, mocker):
    """An error in the SessionResult is surfaced in metrics but handle_message still returns True."""
    fake_result = make_session_result(error="MCE unavailable")

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    result = await worker.handle_message(session_message)

    assert result is True


@pytest.mark.asyncio
async def test_handle_message_fatal_failures_included_in_metrics(rabbit_url, session_message, mocker):
    fail = make_failure_detail("IntentRecognition", 1.0, "intent never resolved", 5, "search_tool")
    fake_result = make_session_result(trajectory_score=0, fatal_failures=[fail])

    mock_processor = mocker.Mock()
    mock_processor.evaluate_trajectory.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)


@pytest.mark.asyncio
async def test_worker_persists_metrics_context_and_session_score(
    rabbit_url, session_message, mocker, no_external_services
):
    smr = SimpleNamespace(
        transition_id="transition:abc",
        span_id="llmcall:1",
        metric_name="Relevancy",
        score=1.0,
        reasoning="ok",
    )
    result = make_session_result(
        trajectory_score=0,
        trajectory_reasoning="Unresolved requirement.",
        span_metric_results=[smr],
    )
    result.transition_contexts = {"transition:abc": {"claims": [{"index": 0}]}}
    processor = mocker.Mock()
    processor.evaluate_trajectory.return_value = result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    save_call = mocker.patch("oxp.providers.OXPMetricsProvider.save_call_metrics", return_value=True)
    save_session = mocker.patch("oxp.providers.OXPMetricsProvider.save_metrics", return_value=True)
    write_context = mocker.patch("oxp.client.dal.write_transition_context", return_value=True)
    worker = _make_worker(rabbit_url)
    worker.push_metrics = True

    await worker.handle_message(session_message)

    save_call.assert_called_once()
    session_id, call_id, metrics = save_call.call_args.args
    assert (session_id, call_id) == (session_message.session_id, "llmcall:1")
    assert [(m.metric_id, m.resource_id, m.provider, m.value, m.reasoning) for m in metrics] == [
        ("Relevancy", "llmcall:1", "StatefulEvals", 1.0, "ok")
    ]
    assert metrics[0].metadata == {}
    write_context.assert_called_once_with(
        no_external_services, session_message.session_id, "transition:abc", {"claims": [{"index": 0}]}
    )
    (session_metrics,) = save_session.call_args.args
    assert [(m.metric_id, m.resource_id, m.provider, m.value, m.reasoning) for m in session_metrics] == [
        ("TrajectoryScore", session_message.session_id, "StatefulEvals", 0, "Unresolved requirement.")
    ]
    assert session_metrics[0].metadata == {"evaluation_model": "gpt-4o"}


@pytest.mark.asyncio
async def test_worker_skips_context_when_disabled(rabbit_url, session_message, mocker):
    result = make_session_result()
    result.transition_contexts = {"transition:abc": {"claims": []}}
    processor = mocker.Mock()
    processor.evaluate_trajectory.return_value = result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    write_context = mocker.patch("oxp.client.dal.write_transition_context")
    mocker.patch("oxp.providers.OXPMetricsProvider.save_metrics", return_value=True)
    worker = _make_worker(rabbit_url)
    worker.push_metrics = True
    worker.push_context = False

    await worker.handle_message(session_message)

    write_context.assert_not_called()


@pytest.mark.asyncio
async def test_worker_does_not_write_when_push_metrics_is_off(rabbit_url, session_message, mocker):
    processor = mocker.Mock()
    processor.evaluate_trajectory.return_value = make_session_result()
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    push = mocker.patch.object(StatefulEvalWorker, "_push_metrics_to_kg")
    worker = _make_worker(rabbit_url)
    worker.push_metrics = False

    await worker.handle_message(session_message)

    push.assert_not_called()


@pytest.mark.asyncio
async def test_worker_persists_session_and_span_evaluation_cost(
    rabbit_url, session_message, mocker, no_external_services
):
    span_metric = SimpleNamespace(
        span_id="span-1",
        span_index=0,
        metric_name="Groundedness",
        score=0.75,
        reasoning="ok",
        evaluation_model="gpt-4o",
        evaluation_prompt_tokens=50,
        evaluation_completion_tokens=5,
        evaluation_total_tokens=55,
        evaluation_cost_usd=0.000175,
    )
    unmeasured = SimpleNamespace(
        span_id="span-2",
        span_index=1,
        metric_name="Relevancy",
        score=0.0,
        reasoning="Auto-failed: span contains error",
        evaluation_model=None,
        evaluation_prompt_tokens=None,
        evaluation_completion_tokens=None,
        evaluation_total_tokens=None,
        evaluation_cost_usd=None,
    )
    result = make_session_result(
        span_metric_results=[span_metric, unmeasured],
        token_usage={"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1200},
        estimated_cost_usd=0.0045,
    )
    processor = mocker.Mock()
    processor.evaluate_trajectory.return_value = result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    worker = _make_worker(rabbit_url, llm_model_name="gpt-4o")
    worker.push_metrics = True
    save_call = mocker.patch("oxp.providers.OXPMetricsProvider.save_call_metrics", return_value=True)
    save_session = mocker.patch("oxp.providers.OXPMetricsProvider.save_metrics", return_value=True)
    mocker.patch("oxp.client.dal.write_transition_context", return_value=True)

    await worker.handle_message(session_message)

    span_metadata = {call.args[1]: call.args[2][0].metadata for call in save_call.call_args_list}
    assert span_metadata["span-1"] == {
        "evaluation_model": "gpt-4o",
        "evaluation_prompt_tokens": 50,
        "evaluation_completion_tokens": 5,
        "evaluation_total_tokens": 55,
        "evaluation_cost_usd": 0.000175,
    }
    assert span_metadata["span-2"] == {}
    (session_metrics,) = save_session.call_args.args
    assert session_metrics[0].metadata == {
        "evaluation_model": "gpt-4o",
        "evaluation_prompt_tokens": 1000,
        "evaluation_completion_tokens": 200,
        "evaluation_total_tokens": 1200,
        "evaluation_cost_usd": 0.0045,
    }


@pytest.mark.asyncio
async def test_worker_does_not_persist_error_results(rabbit_url, session_message, mocker):
    processor = mocker.Mock()
    processor.evaluate_trajectory.return_value = make_session_result(error="evaluation failed")
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    push = mocker.patch.object(StatefulEvalWorker, "_push_metrics_to_kg")
    worker = _make_worker(rabbit_url)
    worker.push_metrics = True

    await worker.handle_message(session_message)

    push.assert_not_called()
    processor.close.assert_called_once()


@pytest.mark.asyncio
async def test_worker_releases_processor_on_unexpected_failure(rabbit_url, session_message, mocker):
    processor = mocker.Mock()
    processor.evaluate_trajectory.side_effect = RuntimeError("unexpected failure")
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    worker = _make_worker(rabbit_url)
    with pytest.raises(RuntimeError, match="unexpected failure"):
        await worker.handle_message(session_message)
    processor.close.assert_called_once()


def test_build_processor_never_fetches_data(rabbit_url, mocker):
    constructor = mocker.patch("stateful_evals_be.TemporalMetricsProcessor")
    worker = _make_worker(rabbit_url)
    assert worker._build_processor() is constructor.return_value
    worker._get_kg.assert_not_called()
