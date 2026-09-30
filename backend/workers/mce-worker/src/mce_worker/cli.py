#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# Load .env BEFORE any other imports so that libraries reading os.environ at
# import time see the correct values.
import os

from dotenv import load_dotenv

_here = os.path.dirname(os.path.abspath(__file__))
# mce-worker/.env (src/mce_worker/../../.env == mce-worker/.env)
_env_file = os.path.join(_here, "..", "..", ".env")
load_dotenv(dotenv_path=os.path.abspath(_env_file), override=False)

import asyncio  # noqa: E402
import logging  # noqa: E402
from typing import Optional  # noqa: E402

import click  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    resolve_max_inflight_messages,
    resolve_neo4j_auth,
    resolve_rabbitmq_url,
)

from mce_worker import queues  # noqa: E402
from mce_worker.worker import MCEWorker  # noqa: E402

logger = logging.getLogger(__name__)


def _resolve_neo4j_uri() -> str:
    explicit_uri = os.getenv("NEO4J_URI")
    if explicit_uri:
        return explicit_uri
    host_value = os.getenv("NEO4J_HOST")
    if not host_value:
        return "bolt://localhost:7687"
    if "://" in host_value:
        return host_value
    port_value = os.getenv("NEO4J_PORT", "7687")
    return f"bolt://{host_value}:{port_value}"


def _build_mce_worker(
    rabbitmq_url: str,
    input_queue: str,
    output_queue: list[str],
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    config_path: Optional[str],
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    neo4j_database: str,
    llm_api_key: Optional[str],
    llm_model_name: Optional[str],
    llm_base_model_url: Optional[str],
    metrics: list[str],
    debug: bool,
) -> MCEWorker:
    return MCEWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=output_queue,
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        max_inflight_messages=max_inflight_messages,
        config_path=config_path,
        neo4j_uri=neo4j_uri,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        neo4j_database=neo4j_database,
        llm_api_key=llm_api_key,
        llm_model_name=llm_model_name,
        llm_base_model_url=llm_base_model_url,
        metrics=metrics,
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
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_MCE_Q} or MCE_INPUT_QUEUE env var)",
)
@click.option(
    "--output-queue",
    type=str,
    multiple=True,
    default=None,
    help="Output queue(s) (default: none — mce is a parallel branch off norm; or MCE_OUTPUT_QUEUE env var)",
)
@click.option(
    "--feedback-queue",
    type=str,
    default=None,
    help="Feedback queue (optional, MCE_FEEDBACK_QUEUE env var)",
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
    default=-1,
    help=(
        "Maximum number of sessions processed concurrently inside one worker "
        "process (-1=auto CPU, env: MAX_INFLIGHT_MESSAGES)"
    ),
)
@click.option(
    "--config-file",
    type=str,
    default=None,
    help="Path to mce_config.yaml (default: MCE_CONFIG_PATH env var)",
)
@click.option(
    "--neo4j-uri",
    type=str,
    default=None,
    help="Neo4j connection URI (default: NEO4J_URI env var)",
)
@click.option(
    "--neo4j-user",
    type=str,
    default=None,
    help="Neo4j username (default: NEO4J_USERNAME env var)",
)
@click.option(
    "--neo4j-password",
    type=str,
    default=None,
    help="Neo4j password (default: NEO4J_PASSWORD env var)",
)
@click.option(
    "--neo4j-database",
    type=str,
    default=None,
    help="Neo4j database name (default: NEO4J_DB env var)",
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
    help="LLM model name (default: LLM_MODEL_NAME env var)",
)
@click.option(
    "--llm-base-model-url",
    type=str,
    default=None,
    help="LLM base URL (default: LLM_BASE_MODEL_URL_MCE env var)",
)
@click.option(
    "--metrics",
    type=str,
    multiple=True,
    default=None,
    help="Metric names to compute (repeatable; default: all configured metrics)",
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
    output_queue: tuple,
    feedback_queue: Optional[str],
    max_sessions: int,
    max_inflight_messages: int,
    config_file: Optional[str],
    neo4j_uri: Optional[str],
    neo4j_user: Optional[str],
    neo4j_password: Optional[str],
    neo4j_database: Optional[str],
    llm_api_key: Optional[str],
    llm_model_name: Optional[str],
    llm_base_model_url: Optional[str],
    metrics: tuple,
    debug: bool,
    run_once: bool,
    input: Optional[str],
    output: Optional[str],
    test: bool,
):
    """Run the MCE (Metrics Computation Engine) Worker for processing telemetry sessions."""
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    input_queue = input_queue or os.getenv("MCE_INPUT_QUEUE", queues.NEW_SESSION_TO_MCE_Q)

    if output_queue:
        output_queue_list = list(output_queue)
    else:
        output_queue_env = os.getenv("MCE_OUTPUT_QUEUE")
        if output_queue_env:
            output_queue_list = output_queue_env.split(",")
        else:
            output_queue_list = []

    feedback_queue = feedback_queue or os.getenv("MCE_FEEDBACK_QUEUE")
    config_path = config_file or os.getenv("MCE_CONFIG_PATH")
    resolved_neo4j_uri = neo4j_uri or _resolve_neo4j_uri()
    resolved_neo4j_user, resolved_neo4j_password = resolve_neo4j_auth(
        neo4j_user,
        neo4j_password,
    )
    resolved_neo4j_database = neo4j_database or os.getenv("NEO4J_DB", "neo4j")
    resolved_llm_api_key = llm_api_key or os.getenv("OPENAI_API_KEY")
    resolved_llm_model_name = llm_model_name or os.getenv("LLM_MODEL_NAME", "gpt-4o")
    resolved_llm_base_model_url = llm_base_model_url or os.getenv("LLM_BASE_MODEL_URL_MCE")
    resolved_max_inflight_messages = resolve_max_inflight_messages(
        max_inflight_messages,
        error_subject="MCE max inflight messages",
    )
    metrics_list = list(metrics) if metrics else []

    logger.info(
        f"Starting MCE Worker: input_queue={input_queue}, output_queue={output_queue_list}, "
        f"config_path={config_path}, debug={debug}"
    )

    worker = _build_mce_worker(
        rabbitmq_url=rabbitmq_url,
        input_queue="run_once" if run_once else input_queue,
        output_queue=output_queue_list,
        feedback_queue=feedback_queue,
        max_sessions=1 if run_once else max_sessions,
        max_inflight_messages=resolved_max_inflight_messages,
        config_path=config_path,
        neo4j_uri=resolved_neo4j_uri,
        neo4j_user=resolved_neo4j_user,
        neo4j_password=resolved_neo4j_password,
        neo4j_database=resolved_neo4j_database,
        llm_api_key=resolved_llm_api_key,
        llm_model_name=resolved_llm_model_name,
        llm_base_model_url=resolved_llm_base_model_url,
        metrics=metrics_list,
        debug=debug,
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
