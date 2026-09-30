#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
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
    original_fetch = StatefulEvalWorker._fetch_spans
    mocker.patch.object(StatefulEvalWorker, "_fetch_spans", return_value=[{"SpanId": "span-1"}])
    mocker.patch.object(
        StatefulEvalWorker,
        "_get_oxp_client",
        return_value=mocker.Mock(spec=["get_session_spans", "write_span_metrics", "write_session_metrics", "close"]),
    )
    return original_fetch


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
    mock_processor.evaluate_spans.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    result = await worker.handle_message(session_message)

    assert result is True


@pytest.mark.asyncio
async def test_handle_message_produces_one_output_message(rabbit_url, session_message, mocker):
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_spans.return_value = fake_result
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
    mock_processor.evaluate_spans.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)

    out = worker.output_messages[0]
    assert out.job_id == session_message.job_id
    assert out.session_id == session_message.session_id
    assert out.workflow_id == session_message.workflow_id


@pytest.mark.asyncio
async def test_handle_message_passes_fetched_spans_with_correct_id(rabbit_url, session_message, mocker):
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_spans.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)

    worker._fetch_spans.assert_called_once_with(session_message.session_id)
    mock_processor.evaluate_spans.assert_called_once_with([{"SpanId": "span-1"}], session_id=session_message.session_id)
    mock_processor.evaluate_session.assert_not_called()
    mock_processor.close.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_builds_processor_once_per_message(rabbit_url, session_message, mocker):
    """A fresh processor is created for each handle_message call."""
    fake_result = make_session_result()

    mock_processor = mocker.Mock()
    mock_processor.evaluate_spans.return_value = fake_result
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
    mock_processor.evaluate_spans.return_value = fake_result
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
    mock_processor.evaluate_spans.return_value = fake_result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=mock_processor)
    mocker.patch("asyncio.to_thread", new=_fake_to_thread)

    worker = _make_worker(rabbit_url)
    await worker.handle_message(session_message)


@pytest.mark.asyncio
async def test_worker_persists_legacy_result_without_changing_payload(rabbit_url, session_message, mocker):
    result = make_session_result(trajectory_score=0, trajectory_reasoning="Unresolved requirement.")
    processor = mocker.Mock()
    processor.evaluate_spans.return_value = result
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    worker = _make_worker(rabbit_url)
    worker.push_metrics = True
    client = worker._get_oxp_client()
    client.write_session_metrics.return_value = {"written": 1, "errors": []}

    await worker.handle_message(session_message)

    client.write_session_metrics.assert_called_once_with(
        session_message.session_id,
        [
            {
                "name": "trajectory_score",
                "value": 0,
                "provider": "stateful_evals",
                "metric_id": None,
                "source": "StatefulEval",
                "reasoning": "Unresolved requirement.",
            }
        ],
    )


@pytest.mark.asyncio
async def test_worker_does_not_persist_error_results(rabbit_url, session_message, mocker):
    processor = mocker.Mock()
    processor.evaluate_spans.return_value = make_session_result(error="evaluation failed")
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
    processor.evaluate_spans.side_effect = RuntimeError("unexpected failure")
    mocker.patch.object(StatefulEvalWorker, "_build_processor", return_value=processor)
    worker = _make_worker(rabbit_url)
    with pytest.raises(RuntimeError, match="unexpected failure"):
        await worker.handle_message(session_message)
    processor.close.assert_called_once()


def test_worker_fetches_and_normalizes_spans(rabbit_url, mocker, no_external_services):
    worker = _make_worker(rabbit_url)
    client = worker._get_oxp_client()
    raw_span = mocker.Mock()
    raw_span.model_dump.return_value = {
        "span_id": "span-1",
        "span_attributes": {"ioa_observe.entity.input": "complete input"},
        "links_trace_id": ["trace-1"],
        "links_span_id": ["sender"],
        "links_trace_state": [""],
        "links_attributes": [{"link.type": "peer_message"}],
    }
    client.get_session_spans.return_value.spans = [raw_span]

    spans = no_external_services(worker, "session-1")

    client.get_session_spans.assert_called_once_with(session_ids=["session-1"], limit=500, offset=0, order="asc")
    assert spans[0]["SpanId"] == "span-1"
    assert spans[0]["SpanAttributes"] == raw_span.model_dump.return_value["span_attributes"]
    assert spans[0]["Links.SpanId"] == ["sender"]
    assert spans[0]["Links.Attributes"] == [{"link.type": "peer_message"}]


def test_build_processor_never_fetches_data(rabbit_url, mocker):
    constructor = mocker.patch("stateful_evals_be.TemporalMetricsProcessor")
    worker = _make_worker(rabbit_url)
    assert worker._build_processor() is constructor.return_value
    worker._get_oxp_client.assert_not_called()
