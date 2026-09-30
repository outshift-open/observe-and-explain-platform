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
from typing import Any, Dict, Optional  # noqa: E402

import click  # noqa: E402
import yaml  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    resolve_rabbitmq_url,
)

from consistency_worker import queues  # noqa: E402
from consistency_worker.worker import ConsistencyWorker  # noqa: E402

logger = logging.getLogger(__name__)


def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path) as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load config file {path}: {e}")
        return None


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
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_CONSISTENCY_Q} or CONSISTENCY_INPUT_QUEUE env var)",
)
@click.option("--feedback-queue", type=str, default=None, help="Feedback queue (optional)")
@click.option(
    "--max-sessions",
    type=int,
    default=-1,
    help="Maximum number of messages to process (-1 for unlimited)",
)
@click.option(
    "--embedding-model",
    "--embedding_model",
    type=str,
    default=None,
    help="Embedding model name (default: EMBEDDING_MODEL env var)",
)
@click.option(
    "--config-file",
    "--config_file",
    type=str,
    default=None,
    help="Path to YAML layers config file (default: CONSISTENCY_CONFIG_FILE env var)",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug mode")
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
    help="Input file path for --run-once mode (JSON ConsistencyInputMessage)",
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
    feedback_queue: Optional[str],
    max_sessions: int,
    embedding_model: Optional[str],
    config_file: Optional[str],
    debug: bool,
    test: bool,
    run_once: bool,
    input_path: Optional[str],
    output_path: Optional[str],
):
    """Run the Consistency Worker."""
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    input_queue = input_queue or os.getenv("CONSISTENCY_INPUT_QUEUE", queues.NEW_SESSION_TO_CONSISTENCY_Q)
    feedback_queue = feedback_queue or os.getenv("CONSISTENCY_FEEDBACK_QUEUE")

    resolved_embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "")

    config_file = config_file or os.getenv("CONSISTENCY_CONFIG_FILE")
    layers = _load_yaml(config_file) if config_file else None

    worker = ConsistencyWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        embedding_model=resolved_embedding_model,
        layers=layers,
        output_queue=[],
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        debug=debug,
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
