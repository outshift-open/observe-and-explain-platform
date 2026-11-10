#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import click
from norm import InMemoryGraph

from rt_norm_worker import worker


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--input",
    "input_path",
    type=click.Path(dir_okay=False),
    default=str(worker.DEFAULT_TRACES_PATH),
    show_default=True,
    help="OTel traces JSON file to read",
)
@click.option(
    "--kind",
    type=click.Choice(["span", "event"]),
    default="span",
    show_default=True,
    help="What each line of the input is: an OTel span (span) or an OTel log record (event)",
)
@click.option(
    "--serve",
    is_flag=True,
    default=False,
    help="Receive spans and logs from the OTel collector (OTLP/HTTP, JSON) instead of reading --input",
)
@click.option("--host", default="0.0.0.0", show_default=True, help="Address to listen on with --serve")
@click.option("--port", type=int, default=4318, show_default=True, help="Port to listen on with --serve")
@click.option("--dry-run", is_flag=True, default=False, help="Use a throwaway in-memory graph instead of Neo4j")
def main(input_path: str, kind: str, serve: bool, host: str, port: int, dry_run: bool):
    """Normalize OTel spans and logs one by one into Neo4j.

    Reads them from a file (--input, --kind), or with --serve receives them from the OTel
    collector's ``otlphttp`` exporter (``encoding: json``) on /v1/traces and /v1/logs."""
    if dry_run:
        graph = InMemoryGraph()
    else:
        from oxp.dependencies import get_neo4j_connector

        from rt_norm_worker.store import Neo4jStore

        graph = Neo4jStore(get_neo4j_connector())
    if serve:
        from rt_norm_worker.server import serve as run_server

        run_server(graph, host, port)
    else:
        worker.run(graph, input_path, kind)


if __name__ == "__main__":
    main()
