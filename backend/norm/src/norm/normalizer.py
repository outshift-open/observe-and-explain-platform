#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Callable
from os import PathLike
from pathlib import Path
from typing import Any, cast

from .ioa_observe import build_kg

OnNormalizedCallback = Callable[
    [list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]], None
]

_on_normalized: OnNormalizedCallback | None = None


def configure(on_normalized: OnNormalizedCallback | None = None) -> None:
    """Configure the library.

    ``on_normalized(spans, nodes, edges)`` is invoked every time
    :func:`normalize` finishes normalizing a trace. Pass ``None`` to clear it.
    """
    global _on_normalized
    _on_normalized = on_normalized


def dump_jsonld(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    path_or_run_id: str | Path | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Build and optionally write a compact JSON-LD document for normalized KG data.

    Delegates to :func:`norm.verifier.nodes_edges_to_jsonld` — the same
    ontology-current IRI mapping ``run_shacl_validation`` feeds to pyshacl —
    so there is a single place that knows how to turn ``(nodes, edges)``
    dicts into JSON-LD.
    """
    from .verifier import nodes_edges_to_jsonld

    doc = nodes_edges_to_jsonld(nodes, edges, run_id="")
    write_path = path if path is not None else path_or_run_id
    if write_path is not None and str(write_path).endswith((".jsonld", ".json")):
        Path(write_path).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return doc


def normalize(
    spans: list[dict[str, Any]],
    **_kwargs: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize raw ClickHouse-shaped OTel spans into ``(nodes, edges)`` JSON dicts.

    Every derived value (application_id, session_id, agent_id, ...) is read
    straight off each span's own ``SpanAttributes`` -- see
    ``norm.ioa_observe`` -- so there is no caller-supplied run_id/override
    plumbing here anymore.
    """
    nodes, edges = build_kg(spans)
    if _on_normalized is not None:
        _on_normalized(spans, nodes, edges)
    return nodes, edges


def load_json(fn: str | PathLike[str]) -> list[dict[str, Any]]:
    """Parse the content of a JSON or JSONL file into a list of span dicts."""
    path = Path(fn)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {fn}")

    with path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    try:
        loaded: Any = json.loads("".join(lines))
        if isinstance(loaded, list):
            return [item for item in cast(list[Any], loaded) if isinstance(item, dict)]
        if isinstance(loaded, dict):
            return [loaded]
        raise ValueError(f"Unsupported JSON payload in {fn}")
    except json.JSONDecodeError:
        return [json.loads(line) for line in lines if line.strip()]


class Normalizer:
    """Thin file-loading convenience wrapper around :func:`normalize`."""

    def process_file(
        self, fn: str | PathLike[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Load a JSON/JSONL span file and normalize it into (nodes, edges)."""
        return normalize(load_json(fn))

    def process_file_json(self, fn: str | PathLike[str]) -> list[dict[str, Any]]:
        """Load a JSON/JSONL span file, normalize it, and return one flat JSON list."""
        nodes, edges = self.process_file(fn)
        return [*nodes, *edges]
