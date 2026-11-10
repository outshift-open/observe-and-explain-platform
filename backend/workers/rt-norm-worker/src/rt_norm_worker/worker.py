#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Protocol

from norm import GraphReader, Kind, StreamNormalizer

from rt_norm_worker.callbacks import Notifier
from rt_norm_worker.rules import RuleSet

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


def process_record(
    graph: Graph, record: dict[str, Any], kind: Kind, notifier: Notifier | None = None
) -> Any:
    """Normalize one span / log record against the graph as stored and write what changed.
    Then, for a log record (``kind="event"``), call back the rules it matches.

    Nothing is kept between records. Returns the ``StreamDelta`` that was applied."""
    print(json.dumps(record))
    delta = StreamNormalizer(graph).process(record, kind)
    print(
        f"  -> +{len(delta.nodes)} nodes, +{len(delta.edges)} edges, "
        f"-{len(delta.removed_nodes)} nodes, -{len(delta.removed_edges)} edges"
    )
    graph.apply(delta)
    if notifier is not None and kind == "event":
        for rule in notifier.notify(record):
            print(f"  => rule {rule.key}: POST {rule.callback_url}")
    return delta


def run(
    graph: Graph,
    path: Path = DEFAULT_TRACES_PATH,
    kind: Kind = "span",
    rules: RuleSet | None = None,
) -> int:
    """Normalize every record of an OTel export file, one by one, into ``graph``.

    ``rules`` is what was loaded from rules.yaml: for logs, each record that matches one is
    POSTed to its callback URL once it is normalized.

    Returns the number of records processed.
    """
    count = 0
    notifier = Notifier(rules) if rules is not None else None
    for record in read_records(path):
        process_record(graph, record, kind, notifier)
        count += 1
    if notifier is not None:
        notifier.close()  # let the pending callbacks finish
    return count
