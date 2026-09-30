#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

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

from intelligence_worker import queues  # noqa: E402
from intelligence_worker.worker import IntelligenceWorker  # noqa: E402

logger = logging.getLogger(__name__)


def _build_intelligence_worker(
    rabbitmq_url: str,
    input_queue: str,
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    periodic_trigger_interval_seconds: float,
    debug: bool,
    catalog_root: str,
    template_max_concurrency: int,
) -> IntelligenceWorker:
    return IntelligenceWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=[],
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        max_inflight_messages=max_inflight_messages,
        periodic_trigger_interval_seconds=periodic_trigger_interval_seconds,
        debug=debug,
        catalog_root=catalog_root,
        template_max_concurrency=template_max_concurrency,
    )


async def run_worker_async(
    rabbitmq_url: str,
    input_queue: str,
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    periodic_trigger_interval_seconds: float,
    debug: bool,
    catalog_root: str,
    template_max_concurrency: int,
):
    worker = _build_intelligence_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        feedback_queue=feedback_queue,
        max_sessions=max_sessions,
        max_inflight_messages=max_inflight_messages,
        periodic_trigger_interval_seconds=periodic_trigger_interval_seconds,
        debug=debug,
        catalog_root=catalog_root,
        template_max_concurrency=template_max_concurrency,
    )
    await worker.run()


async def run_once_mode(
    rabbitmq_url: str,
    input_path: str,
    output_path: str,
    debug: bool,
    catalog_root: str,
    template_max_concurrency: int,
):
    worker = _build_intelligence_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue="argo",
        feedback_queue=None,
        max_sessions=1,
        max_inflight_messages=1,
        periodic_trigger_interval_seconds=600.0,
        debug=debug,
        catalog_root=catalog_root,
        template_max_concurrency=template_max_concurrency,
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
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_INTELLIGENCE_Q} or INTELLIGENCE_INPUT_QUEUE env var)",
)
@click.option(
    "--feedback-queue",
    type=str,
    default=None,
    help="Feedback queue (optional, INTELLIGENCE_FEEDBACK_QUEUE env var)",
)
@click.option(
    "--max-sessions",
    type=int,
    default=-1,
    help="Maximum number of trigger messages to process (-1 for unlimited)",
)
@click.option(
    "--max-inflight-messages",
    type=int,
    default=1,
    help="Maximum number of app jobs processed concurrently inside one worker process (default: 1, -1=auto CPU, env: MAX_INFLIGHT_MESSAGES)",
)
@click.option(
    "--catalog-root",
    type=str,
    default=None,
    help="Root directory containing intelligence catalog templates",
)
@click.option(
    "--template-max-concurrency",
    type=int,
    default=8,
    help="Maximum number of insight templates executed concurrently per trigger",
)
@click.option(
    "--periodic-trigger-interval-seconds",
    type=float,
    default=600.0,
    help="How often (seconds) the worker self-triggers intelligence computation. Also sizes published message TTL (TTL = 1.5x interval).",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
@click.option(
    "--run-once",
    is_flag=True,
    default=False,
    help="Run in single-message mode (process once and exit)",
)
@click.option(
    "--input",
    type=str,
    default=None,
    help="Input file path for --run-once mode (JSON message)",
)
@click.option("--output", type=str, default=None, help="Output file path for --run-once mode")
@click.option("--test", is_flag=True, default=False, help="Test mode: print 'I'm Alive' and exit")
def main(
    rabbitmq_url: Optional[str],
    input_queue: Optional[str],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    catalog_root: Optional[str],
    template_max_concurrency: int,
    periodic_trigger_interval_seconds: float,
    debug: bool,
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    test: bool,
):
    """Run the Intelligence Worker."""

    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    input_queue = input_queue or os.getenv("INTELLIGENCE_INPUT_QUEUE", queues.NEW_SESSION_TO_INTELLIGENCE_Q)
    feedback_queue = feedback_queue or os.getenv("INTELLIGENCE_FEEDBACK_QUEUE")
    resolved_max_inflight_messages = resolve_max_inflight_messages(
        max_inflight_messages,
        error_subject="Intelligence max inflight messages",
    )
    resolved_periodic_trigger_interval_seconds = float(
        os.getenv(
            "PERIODIC_TRIGGER_INTERVAL_SECONDS",
            str(periodic_trigger_interval_seconds),
        )
    )
    resolved_catalog_root = catalog_root or os.getenv("INTELLIGENCE_CATALOG_ROOT", ".")

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
                    catalog_root=resolved_catalog_root,
                    template_max_concurrency=template_max_concurrency,
                )
            )
        else:
            asyncio.run(
                run_worker_async(
                    rabbitmq_url=rabbitmq_url,
                    input_queue=input_queue,
                    feedback_queue=feedback_queue,
                    max_sessions=max_sessions,
                    max_inflight_messages=resolved_max_inflight_messages,
                    periodic_trigger_interval_seconds=resolved_periodic_trigger_interval_seconds,
                    debug=debug,
                    catalog_root=resolved_catalog_root,
                    template_max_concurrency=template_max_concurrency,
                )
            )
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as exc:
        logger.exception("Worker failed with error: %s", exc)
        raise


if __name__ == "__main__":
    main()
