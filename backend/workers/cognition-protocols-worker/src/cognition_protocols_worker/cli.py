# Load .env BEFORE any other imports so that libraries reading os.environ at
# import time see the correct values.
import os

from dotenv import load_dotenv

_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.abspath(os.path.join(_here, "..", "..", ".env")), override=False)

import asyncio  # noqa: E402
import logging  # noqa: E402
from typing import Optional  # noqa: E402

import click  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    resolve_max_inflight_messages,
    resolve_rabbitmq_url,
)

from cognition_protocols_worker import queues  # noqa: E402
from cognition_protocols_worker.worker import CognitionProtocolsWorker  # noqa: E402

logger = logging.getLogger(__name__)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--rabbitmq-url", type=str, default=None, help="RabbitMQ connection URL (default: RABBITMQ_URL env var)")
@click.option(
    "--input-queue",
    type=str,
    default=None,
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_COGNITION_PROTOCOLS_Q} or COGNITION_PROTOCOLS_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help="Output queue(s) (default: none, or COGNITION_PROTOCOLS_OUTPUT_QUEUE env var)",
)
@click.option("--feedback-queue", type=str, default=None, help="Feedback queue (optional, COGNITION_PROTOCOLS_FEEDBACK_QUEUE env var)")
@click.option("--max-sessions", type=int, default=-1, help="Max sessions to process (-1 for unlimited)")
@click.option("--max-inflight-messages", type=int, default=-1, help="Max concurrent messages (-1: auto from CPU count)")
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
@click.option("--run-once", "run_once", is_flag=True, default=False, help="Run in run-once mode (single input message from file)")
@click.option("--input", type=str, default=None, help="Input file path for --run-once mode (JSON message)")
@click.option("--output", type=str, default=None, help="Output file path for --run-once mode")
@click.option("--test", is_flag=True, default=False, help="Test mode: print 'I'm Alive' and exit")
def main(
    rabbitmq_url: Optional[str],
    input_queue: Optional[str],
    output_queue: tuple,
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    debug: bool,
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    test: bool,
):
    """Run the Cognition protocol worker: detect which Cognition protocols a session used (ACCORD, CONCORD, and any plugged in) and evaluate the ones it did."""
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    _rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    _input_queue = input_queue or os.getenv("COGNITION_PROTOCOLS_INPUT_QUEUE", queues.NEW_SESSION_TO_COGNITION_PROTOCOLS_Q)
    if output_queue:
        _output_queue = list(output_queue)
    else:
        output_queue_env = os.getenv("COGNITION_PROTOCOLS_OUTPUT_QUEUE")
        _output_queue = output_queue_env.split(",") if output_queue_env else []
    _feedback_queue = feedback_queue or os.getenv("COGNITION_PROTOCOLS_FEEDBACK_QUEUE")
    _max_inflight = resolve_max_inflight_messages(max_inflight_messages, error_subject="cognition-protocols-worker")

    logger.info("Cognition protocol worker: input=%s output=%s max_inflight=%s run_once=%s", _input_queue, _output_queue, _max_inflight, run_once)

    worker = CognitionProtocolsWorker(
        rabbitmq_url=_rabbitmq_url,
        input_queue="run_once" if run_once else _input_queue,
        output_queue=_output_queue,
        feedback_queue=_feedback_queue,
        message_limit=1 if run_once else max_sessions,
        max_inflight_messages=_max_inflight,
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
        logger.exception("Worker failed with error: %s", exc)
        raise


if __name__ == "__main__":
    main()
