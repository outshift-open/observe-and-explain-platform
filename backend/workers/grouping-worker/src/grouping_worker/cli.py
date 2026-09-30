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
from typing import List, Optional  # noqa: E402

import click  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    resolve_max_inflight_messages,
    resolve_rabbitmq_url,
)

from grouping_worker import queues  # noqa: E402
from grouping_worker.worker import GroupingWorker  # noqa: E402

logger = logging.getLogger(__name__)


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
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_GROUPING_Q} or GROUPING_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help=f"Output queue(s) (default: {queues.NEW_SESSION_TO_ANALYSIS_Q} or GROUPING_OUTPUT_QUEUE env var)",
)
@click.option("--feedback-queue", type=str, default=None, help="Feedback queue (optional)")
@click.option(
    "--max-sessions",
    type=int,
    default=-1,
    help="Maximum number of messages to process (-1 for unlimited)",
)
@click.option(
    "--max-inflight-messages",
    type=int,
    default=16,
    help="Maximum number of queue messages processed concurrently inside one worker process (default: 16, -1=auto CPU, env: MAX_INFLIGHT_MESSAGES)",
)
@click.option(
    "--embedding-model",
    "--embedding_model",
    type=str,
    default=None,
    help="Embedding model name (default: GROUPING_EMBEDDING_MODEL env var)",
)
@click.option(
    "--max-distance",
    "--grouping_max_distance",
    type=float,
    default=None,
    help="Maximum cosine distance for grouping (default: GROUPING_MAX_DISTANCE env var, fallback: 0.3)",
)
@click.option(
    "--max-neighbors",
    "--grouping_max_neighbors",
    type=int,
    default=None,
    help="Maximum number of neighbors to consider (default: GROUPING_MAX_NEIGHBORS env var, fallback: 10)",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
@click.option("--test", is_flag=True, default=False, help="Test mode: print 'I'm Alive' and exit")
@click.option(
    "--run-once",
    is_flag=True,
    default=False,
    help="Run in run-once mode (single input message; Argo Workflows compatible)",
)
@click.option(
    "--input",
    "input_path",
    type=str,
    default=None,
    help="Input file path for --run-once mode (JSON SessionDetailMessage)",
)
@click.option(
    "--output",
    "output_path",
    type=str,
    default=None,
    help="Output file path for --run-once mode",
)
def main(
    rabbitmq_url: Optional[str],
    input_queue: Optional[str],
    output_queue: tuple,
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    embedding_model: Optional[str],
    max_distance: Optional[float],
    max_neighbors: Optional[int],
    debug: bool,
    test: bool,
    run_once: bool,
    input_path: Optional[str],
    output_path: Optional[str],
):
    """Run the Grouping Worker."""
    configure_worker_logging(debug=debug)
    if test:
        print("I'm Alive")
        return

    rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    input_queue = input_queue or os.getenv("GROUPING_INPUT_QUEUE", queues.NEW_SESSION_TO_GROUPING_Q)
    if output_queue:
        output_queue_list: List[str] = list(output_queue)
    else:
        output_queue_env = os.getenv("GROUPING_OUTPUT_QUEUE")
        output_queue_list = output_queue_env.split(",") if output_queue_env else [queues.NEW_SESSION_TO_ANALYSIS_Q]
    feedback_queue = feedback_queue or os.getenv("GROUPING_FEEDBACK_QUEUE")

    resolved_embedding_model = embedding_model or os.getenv("GROUPING_EMBEDDING_MODEL", "azure/text-embedding-3-small")
    resolved_max_distance = (
        max_distance if max_distance is not None else float(os.getenv("GROUPING_MAX_DISTANCE", "0.3"))
    )
    resolved_max_neighbors = (
        max_neighbors if max_neighbors is not None else int(os.getenv("GROUPING_MAX_NEIGHBORS", "10"))
    )
    resolved_max_inflight_messages = resolve_max_inflight_messages(
        max_inflight_messages,
        error_subject="Grouping max inflight messages",
    )

    worker = GroupingWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue_list,
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        embedding_model=resolved_embedding_model,
        max_distance=resolved_max_distance,
        max_neighbors=resolved_max_neighbors,
        debug=debug,
        max_inflight_messages=resolved_max_inflight_messages,
    )

    try:
        if run_once:
            if not input_path:
                raise click.UsageError("--input is required when using --run-once")
            if not output_path:
                raise click.UsageError("--output is required when using --run-once")
            asyncio.run(worker.run_argo_message(input_path, output_path))
        else:
            asyncio.run(worker.run())
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as exc:
        logger.exception(f"Worker failed with error: {exc}")
        raise


if __name__ == "__main__":
    main()
