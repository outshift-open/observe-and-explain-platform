#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from norm import GraphReader, Kind, StreamNormalizer

DEFAULT_TRACES_PATH = Path("~/claris/otel_traces.json").expanduser()


def read_records(path: Path = DEFAULT_TRACES_PATH) -> Iterator[dict[str, Any]]:
    """Yield the records of an OTel export file (a JSON array of span or log objects) one by one."""
    with open(Path(path).expanduser(), encoding="utf-8") as f:
        records = json.load(f)
    if not isinstance(records, list):
        raise ValueError(f"Expected a JSON array in {path}")
    yield from records


class Graph(GraphReader, Protocol):
    """Where the KG lives: read what a span needs, write back what changed."""

    def apply(self, delta: Any) -> None: ...


def process_record(graph: Graph, record: dict[str, Any], kind: Kind) -> Any:
    """Normalize one span / log record against the graph as stored and write what changed.

    Nothing is kept between records. Returns the ``StreamDelta`` that was applied."""
    print(json.dumps(record))
    delta = StreamNormalizer(graph).process(record, kind)
    print(
        f"  -> +{len(delta.nodes)} nodes, +{len(delta.edges)} edges, "
        f"-{len(delta.removed_nodes)} nodes, -{len(delta.removed_edges)} edges"
    )
    graph.apply(delta)
    return delta


def run(graph: Graph, path: Path = DEFAULT_TRACES_PATH, kind: Kind = "span") -> int:
    """Normalize every record of an OTel export file, one by one, into ``graph``.

    Returns the number of records processed.
    """
    count = 0
    for record in read_records(path):
        process_record(graph, record, kind)
        count += 1
    return count
