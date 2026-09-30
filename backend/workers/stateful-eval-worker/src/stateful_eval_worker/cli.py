#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
# Load .env BEFORE any other imports so that libraries reading os.environ at
# import time see the correct values.
import os

from dotenv import load_dotenv

_here = os.path.dirname(os.path.abspath(__file__))
_env_file = os.path.join(_here, "..", "..", ".env")
load_dotenv(dotenv_path=os.path.abspath(_env_file), override=False)

import asyncio  # noqa: E402
import logging  # noqa: E402
from typing import Optional  # noqa: E402

import click  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    resolve_max_inflight_messages,
    resolve_rabbitmq_url,
)

from stateful_eval_worker import queues  # noqa: E402
from stateful_eval_worker.worker import StatefulEvalWorker  # noqa: E402

logger = logging.getLogger(__name__)


def _build_worker(
    rabbit_url: str,
    input_queue: str,
    output_queue: list[str],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    llm_api_key: Optional[str],
    llm_model_name: Optional[str],
    llm_base_model_url: Optional[str],
    debug: bool,
) -> StatefulEvalWorker:
    return StatefulEvalWorker(
        rabbit_url=rabbit_url,
        input_queue=input_queue,
        output_queue=output_queue,
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        max_inflight_messages=max_inflight_messages,
        llm_api_key=llm_api_key,
        llm_model_name=llm_model_name,
        llm_base_model_url=llm_base_model_url,
        debug=debug,
    )


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--rabbitmq-url",
    type=str,
    default=None,
    help="RabbitMQ connection URL (default: RABBITMQ_URL env var)",
)
@click.option(
    "--input-queue",
    type=str,
    default=None,
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_STATEFUL_EVAL_Q} or STATEFUL_EVAL_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help="Output queue(s) (default: none, or STATEFUL_EVAL_OUTPUT_QUEUE env var)",
)
@click.option(
    "--feedback-queue",
    type=str,
    default=None,
    help="Feedback queue (optional, STATEFUL_EVAL_FEEDBACK_QUEUE env var)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=-1,
    help="Max sessions to process (-1 for unlimited)",
)
@click.option(
    "--max-inflight-messages",
    type=int,
    default=32,
    help="Max concurrent in-flight messages (default: auto from CPU count)",
)
@click.option(
    "--llm-api-key",
    type=str,
    default=None,
    help="LLM API key (default: OPENAI_API_KEY env var)",
)
@click.option(
    "--llm-model-name",
    type=str,
    default=None,
    help="LLM model name (default: LLM_MODEL_NAME env var, fallback: gpt-4o)",
)
@click.option(
    "--llm-base-model-url",
    type=str,
    default=None,
    help="LLM base URL (default: LLM_BASE_MODEL_URL_MCE env var)",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging",
)
@click.option(
    "--run-once",
    "run_once",
    is_flag=True,
    default=False,
    help="Run in run-once mode (single input message from file; Argo Workflows compatible)",
)
@click.option(
    "--input",
    type=str,
    default=None,
    help="Input file path for --run-once mode (JSON message)",
)
@click.option(
    "--output",
    type=str,
    default=None,
    help="Output file path for --run-once mode",
)
@click.option(
    "--test",
    is_flag=True,
    default=False,
    help="Test mode: print 'I'm Alive' and exit",
)
def main(
    rabbitmq_url: Optional[str],
    input_queue: Optional[str],
    output_queue: tuple,
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: Optional[int],
    llm_api_key: Optional[str],
    llm_model_name: Optional[str],
    llm_base_model_url: Optional[str],
    debug: bool,
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    test: bool,
):
    """Run the In-Process Stateful Evaluation Worker.

    Computes temporal metrics (Groundedness, IntentRecognition, Relevancy) for
    agent sessions by running TemporalMetricsProcessor directly in-process,
    without requiring the stateful-evals HTTP service.
    """
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    _rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    _input_queue = input_queue or os.getenv(
        "STATEFUL_EVAL_INPUT_QUEUE",
        queues.NEW_SESSION_TO_STATEFUL_EVAL_Q,
    )

    if output_queue:
        _output_queue = list(output_queue)
    else:
        output_queue_env = os.getenv("STATEFUL_EVAL_OUTPUT_QUEUE")
        _output_queue = output_queue_env.split(",") if output_queue_env else []

    _feedback_queue = feedback_queue or os.getenv("STATEFUL_EVAL_FEEDBACK_QUEUE")
    _llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY", "")
    _llm_model_name = llm_model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o")
    _llm_base_model_url = llm_base_model_url or os.getenv("LLM_BASE_MODEL_URL_MCE", "https://api.openai.com/v1")
    _max_inflight = resolve_max_inflight_messages(max_inflight_messages, error_subject="stateful-eval-worker")

    logger.info("=" * 60)
    logger.info("Stateful Eval Worker Configuration")
    logger.info("=" * 60)
    logger.info(f"RabbitMQ URL:        {_rabbitmq_url}")
    logger.info(f"Input Queue:         {_input_queue}")
    logger.info(f"Output Queues:       {_output_queue}")
    logger.info(f"LLM Model:           {_llm_model_name}")
    logger.info(f"Max Inflight:        {_max_inflight}")
    logger.info(f"Debug Mode:          {debug}")
    logger.info(f"Run-once Mode:       {run_once}")
    logger.info("=" * 60)

    worker = _build_worker(
        rabbit_url=_rabbitmq_url,
        input_queue="run_once" if run_once else _input_queue,
        output_queue=_output_queue,
        feedback_queue=_feedback_queue,
        max_sessions=1 if run_once else max_sessions,
        max_inflight_messages=_max_inflight,
        llm_api_key=_llm_api_key,
        llm_model_name=_llm_model_name,
        llm_base_model_url=_llm_base_model_url,
        debug=debug,
    )

    try:
        if run_once:
            if not input or not output:
                raise click.BadParameter("--input and --output are required for --run-once mode")
            asyncio.run(worker.run_argo_message(input, output))
        else:
            asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as exc:
        logger.exception(f"Worker failed with error: {exc}")
        raise


if __name__ == "__main__":
    main()
