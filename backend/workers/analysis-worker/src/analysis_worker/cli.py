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
import json  # noqa: E402
import logging  # noqa: E402
import multiprocessing  # noqa: E402
from typing import Any, Dict, Optional  # noqa: E402

import click  # noqa: E402
import yaml  # noqa: E402
from worker_base.queue_message import SessionGroupMessage  # noqa: E402
from worker_base.utils import (  # noqa: E402
    configure_worker_logging,
    get_available_cpus,
    mask_url_password,
    resolve_rabbitmq_url,
)

from analysis_worker import queues  # noqa: E402
from analysis_worker.worker import AnalysisWorker  # noqa: E402

logger = logging.getLogger(__name__)


def _parse_optional_auto_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    parsed = int(value)
    if parsed == -1:
        return -1
    if parsed <= 0:
        raise click.BadParameter("MAX_INFLIGHT_MESSAGES must be -1 (auto) or a positive integer")
    return parsed


def _run_single_worker(worker_kwargs: Dict[str, Any]) -> None:
    """Run one analysis worker process."""
    worker = AnalysisWorker(**worker_kwargs)
    asyncio.run(worker.run())


def _validate_run_once_input_file(input_path: str) -> tuple[list[dict[str, Any]], bool]:
    """Validate run-once input shape early in the CLI.

    Run-once mode (Argo-compatible) accepts either:
    - a single JSON message object
    - a JSON array of message objects
    """
    try:
        with open(input_path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:
        raise click.BadParameter(f"Failed to read --input JSON file '{input_path}': {exc}") from exc

    if isinstance(payload, dict):
        return [payload], False

    if isinstance(payload, list) and all(isinstance(item, dict) for item in payload):
        return payload, True

    raise click.BadParameter("--input must contain either one JSON message object or a JSON array of message objects")


async def _run_once_mode(
    worker_kwargs: Dict[str, Any],
    input_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> None:
    """Run Analysis worker in run-once mode.

    Supports two variants:
    - File mode (Argo-compatible): requires both input_path and output_path.
    - Queue mode: consumes exactly one queue message and exits.
    """
    run_once_worker_kwargs = dict(worker_kwargs)
    run_once_worker_kwargs["max_inflight_messages"] = 1
    run_once_worker_kwargs["message_limit"] = 1
    # Keep the 3 analysis tracks parallel (anomaly/consistency/normal).
    run_once_worker_kwargs["n_workers"] = max(3, int(run_once_worker_kwargs.get("n_workers", 3)))

    worker = AnalysisWorker(**run_once_worker_kwargs)
    try:
        if input_path is None and output_path is None:
            await worker.run()
            return

        if not input_path or not output_path:
            raise click.UsageError("--input and --output must be provided together in file-based --run-once mode")

        input_messages, is_batch = _validate_run_once_input_file(input_path)

        outputs: list[dict[str, Any]] = []
        for index, raw_message in enumerate(input_messages, start=1):
            message = SessionGroupMessage.model_validate(raw_message)
            if not message.sessions:
                logger.warning(
                    "Run-once message #%d (group %s) has no inline 'sessions'.",
                    index,
                    message.group_id,
                )

            result = await worker.handle_inline_message(message)
            if result is not None:
                outputs.append(
                    result.model_dump(
                        by_alias=True,
                        exclude={"job_id", "local_file"},
                        exclude_none=True,
                    )
                )

        final_payload: Any = outputs if is_batch else (outputs[0] if outputs else {})
        worker._write_argo_output(output_path, final_payload)
    finally:
        worker._close_db_handler()


def _run_worker_process_pool(worker_kwargs: Dict[str, Any], processes: int) -> None:
    """Run N independent worker processes to bypass the GIL for CPU-bound work."""
    children = [multiprocessing.Process(target=_run_single_worker, args=(worker_kwargs,)) for _ in range(processes)]

    for child in children:
        child.start()
    logger.info("Started Analysis Worker process pool with %d workers", processes)

    try:
        while True:
            for child in children:
                child.join(timeout=0.5)
                if child.exitcode is not None:
                    if child.exitcode != 0:
                        raise RuntimeError(f"Analysis worker process {child.pid} exited with code {child.exitcode}")
                    if all(c.exitcode is not None for c in children):
                        return
            if all(c.exitcode is not None for c in children):
                return
    except KeyboardInterrupt:
        logger.info("Stopping analysis worker process pool")
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
        for child in children:
            child.join(timeout=5)


def _load_yaml(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
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
    "--input_queue",
    type=str,
    default=None,
    help=f"Input queue name (default: {queues.NEW_SESSION_TO_ANALYSIS_Q} or ANALYSIS_INPUT_QUEUE env var)",
)
@click.option("--feedback-queue", type=str, default=None, help="Feedback queue (optional)")
@click.option(
    "--max-inflight-messages",
    "--max_inflight_messages",
    type=int,
    default=-1,
    help=(
        "Maximum inflight messages per analysis worker process in server mode "
        "(-1=auto: max(1, cpu_count//3); env: MAX_INFLIGHT_MESSAGES). "
        "This value maps directly to analysis worker process count."
    ),
)
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
    "--anomaly-config-file",
    "--anomaly_config_file",
    type=str,
    default=None,
    help="Path to YAML config file for anomaly detection layers (default: ANOMALY_CONFIG_FILE env var)",
)
@click.option(
    "--consistency-config-file",
    "--consistency_config_file",
    type=str,
    default=None,
    help="Path to YAML config file for consistency layers (default: CONSISTENCY_CONFIG_FILE env var)",
)
@click.option(
    "--normal-behaviour-config-file",
    "--normal_behaviour_config_file",
    type=str,
    default=None,
    help="Path to YAML config file for normal behaviour layers (default: NORMAL_BEHAVIOUR_CONFIG_FILE env var)",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug mode")
@click.option("--test", is_flag=True, default=False, help="Test mode: print 'I'm Alive' and exit")
@click.option(
    "--run-once",
    "run_once",
    is_flag=True,
    default=False,
    help="Run in run-once mode (single input file; Argo Workflows compatible)",
)
@click.option(
    "--input",
    "input_path",
    type=str,
    default=None,
    help="Input file path for --run-once mode (JSON SessionGroupMessage)",
)
@click.option(
    "--output",
    "output_path",
    type=str,
    default=None,
    help="Output file path for --run-once mode",
)
@click.option(
    "--batch_size",
    type=int,
    default=10,
    show_default=True,
    help="Number of sessions to process per batch subprocess (memory tuning parameter)",
)
def main(
    rabbitmq_url: Optional[str],
    input_queue: Optional[str],
    feedback_queue: Optional[str],
    max_inflight_messages: int,
    max_sessions: int,
    embedding_model: Optional[str],
    anomaly_config_file: Optional[str],
    consistency_config_file: Optional[str],
    normal_behaviour_config_file: Optional[str],
    debug: bool,
    test: bool,
    run_once: bool,
    input_path: Optional[str],
    output_path: Optional[str],
    batch_size: int,
):
    """Run the Analysis Worker (CPU-bound anomaly detection + consistency + normal behaviour).

    Uses multiprocessing to parallelize CPU-bound analysis work across multiple processes,
    each with API-managed connector state in-process. Concurrency is limited to
    prevent Neo4j connection exhaustion.
    """
    configure_worker_logging(debug=debug)

    if test:
        print("I'm Alive")
        return

    rabbitmq_url = resolve_rabbitmq_url(rabbitmq_url)
    input_queue = input_queue or os.getenv("ANALYSIS_INPUT_QUEUE", queues.NEW_SESSION_TO_ANALYSIS_Q)
    feedback_queue = feedback_queue or os.getenv("ANALYSIS_FEEDBACK_QUEUE")

    # The three analysis tracks (anomaly/consistency/normal behaviour) must run in parallel.
    resolved_analysis_concurrency = 3

    resolved_max_inflight_messages = max_inflight_messages
    if resolved_max_inflight_messages == -1:
        env_value = _parse_optional_auto_int(os.getenv("MAX_INFLIGHT_MESSAGES"))
        if env_value is not None:
            resolved_max_inflight_messages = env_value

    if resolved_max_inflight_messages == -1:
        available_cpus = get_available_cpus()
        resolved_max_inflight_messages = max(1, available_cpus // 3)

    if resolved_max_inflight_messages <= 0:
        raise ValueError("--max-inflight-messages/--max_inflight_messages must be -1 (auto) or a positive integer")

    resolved_embedding_model = embedding_model or os.getenv("EMBEDDING_MODEL", "")

    anomaly_config_file = anomaly_config_file or os.getenv("ANOMALY_CONFIG_FILE")
    consistency_config_file = consistency_config_file or os.getenv("CONSISTENCY_CONFIG_FILE")
    normal_behaviour_config_file = normal_behaviour_config_file or os.getenv("NORMAL_BEHAVIOUR_CONFIG_FILE")

    anomaly_layers = _load_yaml(anomaly_config_file) if anomaly_config_file else None
    consistency_layers = _load_yaml(consistency_config_file) if consistency_config_file else None
    normal_behaviour_layers = _load_yaml(normal_behaviour_config_file) if normal_behaviour_config_file else None

    # Log config file contents
    if anomaly_config_file:
        logger.info(
            "ANOMALY_CONFIG_FILE (%s):\n%s",
            anomaly_config_file,
            yaml.dump(anomaly_layers, default_flow_style=False),
        )
    else:
        logger.info("ANOMALY_CONFIG_FILE: not provided (using defaults)")

    if consistency_config_file:
        logger.info(
            "CONSISTENCY_CONFIG_FILE (%s):\n%s",
            consistency_config_file,
            yaml.dump(consistency_layers, default_flow_style=False),
        )
    else:
        logger.info("CONSISTENCY_CONFIG_FILE: not provided (using defaults)")

    if normal_behaviour_config_file:
        logger.info(
            "NORMAL_BEHAVIOUR_CONFIG_FILE (%s):\n%s",
            normal_behaviour_config_file,
            yaml.dump(normal_behaviour_layers, default_flow_style=False),
        )
    else:
        logger.info("NORMAL_BEHAVIOUR_CONFIG_FILE: not provided (using defaults)")

    # Global target:
    # - N inflight messages configured
    # - 3 analysis tracks per message
    # => process pool size = N * 3
    # Keep one queue message in-flight per process for clearer queue observability.
    resolved_max_inflight_per_process = 1
    resolved_max_processes = resolved_max_inflight_messages * resolved_analysis_concurrency

    logger.info("=" * 60)
    logger.info("Analysis Worker Configuration")
    logger.info("=" * 60)
    logger.info("RabbitMQ URL: %s", mask_url_password(rabbitmq_url))
    logger.info("Input Queue: %s", input_queue)
    logger.info("Feedback Queue: %s", feedback_queue)
    logger.info("Embedding Model: %s", resolved_embedding_model)
    logger.info("Analysis Track Concurrency: %s", resolved_analysis_concurrency)
    logger.info("Max Inflight Messages: %s", resolved_max_inflight_messages)
    logger.info("Process Count: %s", resolved_max_processes)
    logger.info("Max Sessions: %s", max_sessions)
    logger.info("Batch Size: %s", batch_size)
    logger.info("Debug Mode: %s", debug)
    logger.info("=" * 60)

    worker_kwargs = dict(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        embedding_model=resolved_embedding_model,
        n_workers=resolved_analysis_concurrency,
        max_inflight_messages=resolved_max_inflight_per_process,
        batch_size=batch_size,
        anomaly_layers=anomaly_layers,
        consistency_layers=consistency_layers,
        normal_behaviour_layers=normal_behaviour_layers,
        output_queue=[],
        feedback_queue=feedback_queue,
        message_limit=max_sessions,
        debug=debug,
    )

    try:
        if run_once:
            asyncio.run(_run_once_mode(worker_kwargs, input_path, output_path))
        else:
            if resolved_max_processes <= 1:
                worker = AnalysisWorker(**worker_kwargs)
                asyncio.run(worker.run())
            else:
                _run_worker_process_pool(worker_kwargs, resolved_max_processes)
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception:
        logger.exception("Worker failed")
        raise


if __name__ == "__main__":
    main()
