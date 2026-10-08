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
@click.option("--dry-run", is_flag=True, default=False, help="Use a throwaway in-memory graph instead of Neo4j")
def main(input_path: str, dry_run: bool):
    """Read the OTel traces file and normalize the spans one by one into Neo4j."""
    if dry_run:
        graph = InMemoryGraph()
    else:
        from oxp.dependencies import get_neo4j_connector

        from rt_norm_worker.store import Neo4jStore

        graph = Neo4jStore(get_neo4j_connector())
    worker.run(graph, input_path)


if __name__ == "__main__":
    main()
