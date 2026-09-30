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
from worker_base.utils import configure_worker_logging  # noqa: E402

from hierarchical_grouping_worker import queues  # noqa: E402
from hierarchical_grouping_worker.worker import HierarchicalGroupingWorker  # noqa: E402

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
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_PERIODIC_GROUPING_Q} or HIERARCHICAL_GROUPING_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help=f"Output queue(s) (default: {queues.NEW_SESSION_TO_ANALYSIS_Q} or HIERARCHICAL_GROUPING_OUTPUT_QUEUE env var)",
)
@click.option("--feedback-queue", type=str, default=None, help="Feedback queue (optional)")
@click.option("--llm-base-url", type=str, default=None, help="LLM base URL")
@click.option("--llm-model-name", type=str, default=None, help="LLM model name")
@click.option("--llm-api-key", type=str, default=None, help="LLM API key")
@click.option("--embedding-model", type=str, default=None, help="Embedding model name")
@click.option(
    "--max-inflight-messages",
    type=int,
    default=1,
    help="Maximum number of app jobs processed concurrently inside one worker process",
)
@click.option(
    "--max-neighbors",
    type=int,
    default=None,
    help="Maximum neighbors for semantic grouping",
)
@click.option(
    "--min-samples",
    type=int,
    default=20,
    help="Minimum number of samples required for grouping",
)
@click.option(
    "--max-distance",
    type=float,
    default=0.15,
    help="Maximum distance for semantic grouping",
)
@click.option(
    "--periodic-trigger-interval-seconds",
    type=float,
    default=600.0,
    help="How often (seconds) the worker self-triggers a grouping computation. Also sizes the TTL on published messages (TTL = 1.5x interval).",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging")
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
@click.option("--test", is_flag=True, default=False, help="Test mode: print 'I'm Alive' and exit")
def main(
    rabbitmq_url: Optional[str],
    input_queue: Optional[str],
    output_queue: tuple[str, ...],
    feedback_queue: Optional[str],
    llm_base_url: Optional[str],
    llm_model_name: Optional[str],
    llm_api_key: Optional[str],
    embedding_model: Optional[str],
    max_inflight_messages: int,
    max_neighbors: Optional[int],
    min_samples: int,
    max_distance: float,
    periodic_trigger_interval_seconds: float,
    debug: bool,
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    test: bool,
):
    """Run the Hierarchical Grouping Worker."""
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    rabbitmq_url = rabbitmq_url or os.getenv("RABBITMQ_URL")
    input_queue = input_queue or os.getenv(
        "HIERARCHICAL_GROUPING_INPUT_QUEUE", queues.NEW_SESSION_TO_PERIODIC_GROUPING_Q
    )
    if output_queue:
        output_queue_list = list(output_queue)
    else:
        output_queue_env = os.getenv("HIERARCHICAL_GROUPING_OUTPUT_QUEUE")
        if output_queue_env:
            output_queue_list = output_queue_env.split(",")
        else:
            output_queue_list = [queues.NEW_SESSION_TO_ANALYSIS_Q]

    feedback_queue = feedback_queue or os.getenv("HIERARCHICAL_GROUPING_FEEDBACK_QUEUE")
    resolved_llm_base_url = llm_base_url or os.getenv("LLM_BASE_MODEL_URL_MCE", "")
    resolved_llm_model_name = llm_model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o")
    resolved_llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY", "")
    resolved_embedding_model = embedding_model or os.getenv(
        "HIERARCHICAL_GROUPING_EMBEDDING_MODEL", "azure/text-embedding-3-small"
    )
    resolved_max_inflight_messages = int(
        os.getenv(
            "MAX_INFLIGHT_MESSAGES",
            str(max_inflight_messages),
        )
    )
    resolved_max_neighbors = max_neighbors or int(os.getenv("HIERARCHICAL_GROUPING_MAX_NEIGHBORS", "10"))
    resolved_min_samples = int(os.getenv("HIERARCHICAL_GROUPING_MIN_SAMPLES", str(min_samples)))
    resolved_max_distance = float(os.getenv("HIERARCHICAL_GROUPING_MAX_DISTANCE", str(max_distance)))
    resolved_periodic_trigger_interval_seconds = float(
        os.getenv(
            "PERIODIC_TRIGGER_INTERVAL_SECONDS",
            str(periodic_trigger_interval_seconds),
        )
    )

    worker = HierarchicalGroupingWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue_list,
        feedback_queue=feedback_queue,
        llm_base_url=resolved_llm_base_url,
        llm_model_name=resolved_llm_model_name,
        llm_api_key=resolved_llm_api_key,
        embedding_model=resolved_embedding_model,
        max_inflight_messages=resolved_max_inflight_messages,
        max_neighbors=resolved_max_neighbors,
        min_samples=resolved_min_samples,
        max_distance=resolved_max_distance,
        debug=debug,
        periodic_trigger_interval_seconds=resolved_periodic_trigger_interval_seconds,
    )

    try:
        if run_once:
            if not input or not output:
                raise ValueError("--run-once mode requires both --input and --output file paths")
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
