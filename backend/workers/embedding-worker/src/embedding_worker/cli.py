#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Load .env BEFORE any other imports so that libraries reading os.environ at
# import time see the correct values.
import os

from dotenv import load_dotenv

_here = os.path.dirname(os.path.abspath(__file__))
# embedding-worker/.env (src/embedding_worker/../../.env == embedding-worker/.env)
_env_file = os.path.join(_here, "..", "..", ".env")
# Keep runtime-provided env vars (e.g. docker --env-file/-e) as precedence.
load_dotenv(dotenv_path=os.path.abspath(_env_file), override=False)

import asyncio  # noqa: E402
import logging  # noqa: E402
from typing import TYPE_CHECKING, Optional  # noqa: E402

import click  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    mask_url_password,
    resolve_max_inflight_messages,
    resolve_rabbitmq_url,
)

from embedding_worker import queues  # noqa: E402

if TYPE_CHECKING:
    from worker_base.base_worker import BaseWorker

logger = logging.getLogger(__name__)


def _build_embedding_worker(
    rabbitmq_url: str,
    input_queue: str,
    output_queue: Optional[list[str]],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    debug: bool,
    embedder_type: Optional[str],
    embedding_model: Optional[str],
) -> "BaseWorker":
    """Build and return an EmbeddingWorker instance."""
    from embedding_worker import worker

    return worker.EmbeddingWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue or [],
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        max_inflight_messages=max_inflight_messages,
        debug=debug,
        embedder=embedder_type,
        model=embedding_model,
    )


async def run_worker_async(
    rabbitmq_url: str,
    input_queue: str,
    output_queue: Optional[list[str]],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    debug: bool,
    embedder_type: Optional[str],
    embedding_model: Optional[str],
):
    """Run the worker asynchronously."""
    worker = _build_embedding_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue,
        feedback_queue=feedback_queue,
        max_sessions=max_sessions,
        max_inflight_messages=max_inflight_messages,
        debug=debug,
        embedder_type=embedder_type,
        embedding_model=embedding_model,
    )
    await worker.run()


async def run_once_mode(
    rabbitmq_url: str,
    input_path: str,
    output_path: str,
    debug: bool,
    embedder_type: Optional[str],
    embedding_model: Optional[str],
):
    """Run worker in run-once mode (Argo-compatible, single message)."""
    worker = _build_embedding_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue="run_once",
        output_queue=[],
        feedback_queue=None,
        max_sessions=1,
        max_inflight_messages=1,
        debug=debug,
        embedder_type=embedder_type,
        embedding_model=embedding_model,
    )
    await worker.run_argo_message(input_path, output_path)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--rabbitmq-url",
    "--rabbitmq_url",
    type=str,
    default=None,
    help="RabbitMQ connection URL (default: RABBITMQ_URL env var)",
)
@click.option(
    "--input-queue",
    type=str,
    default=None,
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_EMB_Q} or EMBEDDING_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help=f"Output queues (default: {queues.NEW_SESSION_TO_GROUPING_Q} or EMBEDDING_OUTPUT_QUEUE env var)",
)
@click.option(
    "--feedback-queue",
    type=str,
    default=None,
    help="Feedback queue for processing notifications (optional, EMBEDDING_FEEDBACK_QUEUE env var)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=-1,
    help="Maximum number of sessions to process (-1 for unlimited)",
)
@click.option(
    "--max-inflight-messages",
    type=int,
    default=16,
    help=(
        "Maximum number of sessions processed concurrently inside one worker "
        "process (default: 16, -1=auto CPU, env: MAX_INFLIGHT_MESSAGES). Each "
        "in-flight session issues one batched call to the embedding API, so "
        "this also caps per-process concurrent API requests."
    ),
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug mode with detailed logging and embeddings dump",
)
@click.option(
    "--embedder-type",
    type=str,
    default=None,
    help="Embedder type (default: SentenceTransformerEmbedder or EMBEDDING_EMBEDDER_TYPE env var)",
)
@click.option(
    "--embedding-model",
    type=str,
    default=None,
    help="Model identifier for embeddings (default: all-MiniLM-L6-v2 or EMBEDDING_MODEL env var)",
)
@click.option(
    "--run-once",
    "run_once",
    is_flag=True,
    default=False,
    help="Run in run-once mode (single input message; Argo Workflows compatible)",
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
    max_inflight_messages: int,
    debug: bool,
    embedder_type: Optional[str],
    embedding_model: Optional[str],
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    test: bool,
):
    """Run the Embedding Worker for processing telemetry sessions with embeddings."""

    # Set up logging
    configure_worker_logging(debug=debug)

    # Test mode
    if test:
        print("I'm Alive")
        return

    # Get configuration from environment with CLI overrides
    _rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    _input_queue = input_queue or os.getenv("EMBEDDING_INPUT_QUEUE", queues.NEW_SESSION_TO_EMB_Q)
    _output_queue = (
        list(output_queue)
        if output_queue
        else (os.getenv("EMBEDDING_OUTPUT_QUEUE", queues.NEW_SESSION_TO_GROUPING_Q).split(","))
    )
    _feedback_queue = feedback_queue or os.getenv("EMBEDDING_FEEDBACK_QUEUE")
    _embedder_type = embedder_type or os.getenv("EMBEDDING_EMBEDDER_TYPE", "SentenceTransformerEmbedder")
    _embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    _max_inflight_messages = resolve_max_inflight_messages(
        max_inflight_messages,
        error_subject="Embedding max inflight messages",
    )

    logger.info("=" * 60)
    logger.info("Embedding Worker Configuration")
    logger.info("=" * 60)
    logger.info(f"RabbitMQ URL: {mask_url_password(_rabbitmq_url)}")
    logger.info(f"Input Queue: {_input_queue}")
    logger.info(f"Output Queues: {_output_queue}")
    logger.info(f"Embedder Type: {_embedder_type}")
    logger.info(f"Embedding Model: {_embedding_model}")
    logger.info(f"Max Inflight Messages: {_max_inflight_messages}")
    logger.info(f"Debug Mode: {debug}")
    logger.info("=" * 60)

    # Validate run-once mode requirements
    if run_once:
        if not input or not output:
            raise click.BadParameter("--input and --output are required for --run-once mode")
        asyncio.run(
            run_once_mode(
                rabbitmq_url=_rabbitmq_url,
                input_path=input,
                output_path=output,
                debug=debug,
                embedder_type=_embedder_type,
                embedding_model=_embedding_model,
            )
        )
    else:
        asyncio.run(
            run_worker_async(
                rabbitmq_url=_rabbitmq_url,
                input_queue=_input_queue,
                output_queue=_output_queue,
                feedback_queue=_feedback_queue,
                max_sessions=max_sessions,
                max_inflight_messages=_max_inflight_messages,
                debug=debug,
                embedder_type=_embedder_type,
                embedding_model=_embedding_model,
            )
        )


if __name__ == "__main__":
    main()
