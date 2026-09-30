#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

"""Standalone test that runs the worker and logs all Neo4j writes to JSON.

Usage:
    python tests/test_worker_writes_to_json.py --session-id <session-id> --output <output.json>

This script:
1. Runs the worker without any mocks
2. Intercepts Neo4j writes by patching at the DAL layer
3. Logs all writes (nodes and edges) to a JSON file
"""

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

from norm_worker.worker import NormWorker
from norm_worker.wrapper import norm_wrapper as norm_wrapper_module

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class Neo4jWriteLogger:
    """Captures all Neo4j writes without mocking the actual operations."""

    def __init__(self):
        self.writes: List[Dict[str, Any]] = []
        self.original_ingest = None

    def setup_hook(self):
        """Install the logging hook into the wrapper module."""
        from oxp.client.dal import ingest_normalized_kg

        self.original_ingest = ingest_normalized_kg

        def logging_ingest_normalized_kg(db, nodes, edges, run_id, override, batch_size=200):
            """Log nodes and edges before writing to Neo4j."""
            logger.info(f"Intercepted Neo4j write: run_id={run_id}, nodes={len(nodes)}, edges={len(edges)}")

            write_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "override": override,
                "batch_size": batch_size,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "nodes": [json.loads(json.dumps(n, default=str)) for n in nodes],
                "edges": [json.loads(json.dumps(e, default=str)) for e in edges],
            }
            self.writes.append(write_record)

            # Call the real ingest function
            try:
                result = self.original_ingest(db, nodes, edges, run_id, override, batch_size)
                logger.info(f"Neo4j write succeeded: run_id={run_id}")
                return result
            except Exception as exc:
                logger.error(f"Neo4j write failed: run_id={run_id}, error={exc}")
                raise

        # Monkey-patch the ingest function
        norm_wrapper_module.oxp_api_ingest_normalized_kg = logging_ingest_normalized_kg
        logger.info("Neo4j write logger hook installed")

    def get_log_data(self, session_id: str, worker_result: Any = None) -> Dict[str, Any]:
        """Get the formatted log data."""
        return {
            "test": "worker_neo4j_writes_integration",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "worker_result": str(worker_result),
            "summary": {
                "total_write_operations": len(self.writes),
                "total_nodes": sum(w.get("node_count", 0) for w in self.writes),
                "total_edges": sum(w.get("edge_count", 0) for w in self.writes),
            },
            "writes": self.writes,
        }


async def run_worker_test(session_id: str, output_file: str) -> None:
    """Run the worker and log writes to JSON."""
    logger.info(f"Starting worker test for session_id={session_id}")

    # Set up logging hook
    logger_hook = Neo4jWriteLogger()
    logger_hook.setup_hook()

    # Create worker with environment settings
    rabbitmq_url = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost/")
    input_queue = os.getenv("NORM_INPUT_QUEUE", "new_session_in")

    worker = NormWorker(
        rabbitmq_url=rabbitmq_url,
        input_queue=input_queue,
        output_queue=[],  # No output needed for this test
    )

    # Create message
    msg = SimpleNamespace(session_id=session_id, local_file=None)

    # Run the worker
    try:
        result = await worker.handle_message(msg)
        logger.info(f"Worker completed with result={result}")
    except Exception as exc:
        logger.error(f"Worker failed: {exc}", exc_info=True)
        result = f"FAILED: {exc}"

    # Write log file
    log_data = logger_hook.get_log_data(session_id, result)

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(log_data, f, indent=2, default=str)

    logger.info(f"Writes logged to {output_path}")
    logger.info(f"Summary: {log_data['summary']}")

    # Print to stdout as well
    print("\n" + "=" * 80)
    print("NEO4J WRITES LOG")
    print("=" * 80)
    print(json.dumps(log_data, indent=2, default=str))
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Run worker and log Neo4j writes to JSON",
    )
    parser.add_argument(
        "--session-id",
        required=True,
        help="Session ID to process",
    )
    parser.add_argument(
        "--output",
        default="neo4j_writes.json",
        help="Output JSON file path (default: neo4j_writes.json)",
    )

    args = parser.parse_args()

    asyncio.run(run_worker_test(args.session_id, args.output))


if __name__ == "__main__":
    main()
