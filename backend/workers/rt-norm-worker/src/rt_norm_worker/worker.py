#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from norm import GraphReader, StreamNormalizer

DEFAULT_TRACES_PATH = Path("~/claris/otel_traces.json").expanduser()


def read_spans(path: Path = DEFAULT_TRACES_PATH) -> Iterator[dict[str, Any]]:
    """Yield the spans stored in an OTel export file (a JSON array of span objects) one by one."""
    with open(Path(path).expanduser(), encoding="utf-8") as f:
        spans = json.load(f)
    if not isinstance(spans, list):
        raise ValueError(f"Expected a JSON array of spans in {path}")
    yield from spans


class Graph(GraphReader, Protocol):
    """Where the KG lives: read what a span needs, write back what changed."""

    def apply(self, delta: Any) -> None: ...


def run(graph: Graph, path: Path = DEFAULT_TRACES_PATH) -> int:
    """Print every span, normalize it on its own and write only what changed to ``graph``.

    Nothing is kept between spans: each one is normalized against the graph as stored.

    Returns the number of spans processed.
    """
    count = 0
    for span in read_spans(path):
        print(json.dumps(span))
        delta = StreamNormalizer(graph).process(span)
        print(
            f"  -> +{len(delta.nodes)} nodes, +{len(delta.edges)} edges, "
            f"-{len(delta.removed_nodes)} nodes, -{len(delta.removed_edges)} edges"
        )
        graph.apply(delta)
        count += 1
    return count
