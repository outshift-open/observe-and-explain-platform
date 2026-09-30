#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Load .env BEFORE any other imports so that libraries reading os.environ at
# import time see the correct values.
import os

from dotenv import load_dotenv

_here = os.path.dirname(os.path.abspath(__file__))
# norm-worker/.env (src/norm_worker/../../.env == norm-worker/.env)
_env_file = os.path.join(_here, "..", "..", ".env")
# Keep runtime-provided env vars (e.g. docker --env-file/-e) as precedence.
load_dotenv(dotenv_path=os.path.abspath(_env_file), override=False)

import asyncio  # noqa: E402
import logging  # noqa: E402
from typing import Optional  # noqa: E402

import click  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from worker_base.base_worker import BaseWorker  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    mask_url_password,
    resolve_max_inflight_messages,
    resolve_rabbitmq_url,
)

from norm_worker import queues, worker  # noqa: E402

logger = logging.getLogger(__name__)


class NormWorkerCLIArgs(BaseModel):
    """Configuration for the Normalization Worker CLI."""

    rabbitmq_url: Optional[str] = Field(None, description="RabbitMQ connection URL (amqp://...)")
    input_queue: Optional[str] = Field(None, description="Input queue name for sessions")
    output_queue: Optional[list[str]] = Field(None, description="Output queues for processed sessions")
    feedback_queue: Optional[str] = Field(None, description="Feedback queue for processing notifications")
    max_sessions: Optional[int] = Field(-1, description="Maximum number of sessions to process (-1 for unlimited)")
    max_inflight_messages: Optional[int] = Field(
        10,
        description="Maximum number of sessions processed concurrently within a single worker process",
    )
    debug: Optional[bool] = Field(False, description="Enable debug mode with detailed logging and file dumps")
    override: Optional[bool] = Field(
        False,
        description="Override existing data in normalization database (useful for re-processing)",
    )
    run_once: Optional[bool] = Field(
        False,
        description="Whether to process a single input message in run-once mode (Argo-compatible) without using queues",
    )
    input: Optional[str] = Field(None, description="Run-once input file path (JSON message file)")
    output: Optional[str] = Field(None, description="Run-once output file path for the processed message")
    kg_output: Optional[str] = Field(
        None,
        description="Also save the KG as JSON to this path (always pushed to Neo4j)",
    )
    test: Optional[bool] = Field(False, description="Test mode: print 'I'm Alive' and exit")


def _build_norm_worker(
    rabbitmq_url: str,
    input_queue: str,
    output_queue: Optional[list[str]],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    debug: bool,
    override: bool,
    kg_output: Optional[str] = None,
) -> BaseWorker:
    """Build and return a NormWorker instance."""
    return worker.NormWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue or [],
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        max_inflight_messages=max_inflight_messages,
        debug=debug,
        override=override,
        kg_output=kg_output,
    )


async def run_worker_async(
    rabbitmq_url: str,
    input_queue: str,
    output_queue: Optional[list[str]],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    debug: bool,
    override: bool,
    kg_output: Optional[str] = None,
):
    """Run the worker asynchronously."""
    worker = _build_norm_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue,
        feedback_queue=feedback_queue,
        max_sessions=max_sessions,
        max_inflight_messages=max_inflight_messages,
        debug=debug,
        override=override,
        kg_output=kg_output,
    )
    await worker.run()


async def run_once_mode(
    rabbitmq_url: str,
    input_path: str,
    output_path: str,
    debug: bool,
    override: bool,
    kg_output: Optional[str] = None,
):
    """Run worker in run-once mode (Argo-compatible, single message)."""
    worker = _build_norm_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue="argo",
        output_queue=[],
        feedback_queue=None,
        max_sessions=1,
        max_inflight_messages=1,
        debug=debug,
        override=override,
        kg_output=kg_output,
    )
    await worker.run_argo_message(input_path, output_path)


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
    help=f"Input queue name (default: {queues.NEW_SESSION_IN_Q} or NORM_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help=f"Output queues (default: {queues.NEW_SESSION_TO_MCE_Q}, {queues.NEW_SESSION_TO_EMB_Q} or NORM_OUTPUT_QUEUE env var)",
)
@click.option(
    "--feedback-queue",
    type=str,
    default=None,
    help="Feedback queue for processing notifications (optional, NORM_FEEDBACK_QUEUE env var)",
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
    default=32,
    help="Maximum number of sessions processed concurrently inside one worker process (default: 32, -1=auto CPU, env: MAX_INFLIGHT_MESSAGES)",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug mode with detailed logging and file dumps",
)
@click.option(
    "--override",
    is_flag=True,
    default=False,
    help="Override existing data in normalization database (for re-processing)",
)
@click.option(
    "--run-once",
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
    "--kg-output",
    type=str,
    default=None,
    help="Also save the normalized KG as JSON to this path (always pushed to Neo4j)",
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
    override: bool,
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    kg_output: Optional[str],
    test: bool,
):
    """Run the Normalization Worker for processing telemetry sessions."""

    # Set up logging
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    # Get values from environment variables if not provided
    rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    input_queue = input_queue or os.getenv("NORM_INPUT_QUEUE", queues.NEW_SESSION_IN_Q)

    if output_queue:
        output_queue_list = list(output_queue)
    else:
        output_queue_env = os.getenv("NORM_OUTPUT_QUEUE")
        if output_queue_env:
            output_queue_list = output_queue_env.split(",")
        else:
            output_queue_list = [
                queues.NEW_SESSION_TO_MCE_Q,
                queues.NEW_SESSION_TO_EMB_Q,
            ]

    feedback_queue = feedback_queue or os.getenv("NORM_FEEDBACK_QUEUE")
    resolved_max_inflight_messages = resolve_max_inflight_messages(
        max_inflight_messages,
        error_subject="Normalisation max inflight messages",
    )

    logger.info("=" * 60)
    logger.info("Normalization Worker Configuration")
    logger.info("=" * 60)
    logger.info("RabbitMQ URL: %s", mask_url_password(rabbitmq_url))
    logger.info("Input Queue: %s", input_queue)
    logger.info("Output Queue: %s", output_queue_list)
    logger.info("Feedback Queue: %s", feedback_queue)
    logger.info("Max Inflight Messages: %s", resolved_max_inflight_messages)
    logger.info("Max Sessions: %s", max_sessions)
    logger.info("KG Save Path: %s", kg_output)
    logger.info("Override Mode: %s", override)
    logger.info("Debug Mode: %s", debug)
    logger.info("=" * 60)

    try:
        if run_once:
            if not input or not output:
                raise ValueError("--run-once mode requires both --input and --output file paths")
            asyncio.run(
                run_once_mode(
                    rabbitmq_url=rabbitmq_url,
                    input_path=input,
                    output_path=output,
                    debug=debug,
                    override=override,
                    kg_output=kg_output,
                )
            )
        else:
            asyncio.run(
                run_worker_async(
                    rabbitmq_url=rabbitmq_url,
                    input_queue=input_queue,
                    output_queue=output_queue_list,
                    feedback_queue=feedback_queue,
                    max_sessions=max_sessions,
                    max_inflight_messages=resolved_max_inflight_messages,
                    debug=debug,
                    override=override,
                    kg_output=kg_output,
                )
            )
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.exception(f"Worker failed with error: {e}")
        raise


if __name__ == "__main__":
    main()
