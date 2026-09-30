#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from norm import normalize
from oxp.client.local import LocalClient as OXPLocalClient
from oxp.dependencies import get_db

logger = logging.getLogger(__name__)


class NormDALHandler(Protocol):
    def ingest_normalized_kg(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        run_id: str,
        override: bool,
        batch_size: int = 200,
    ) -> bool: ...


def _to_otel_span_dict(span: Any) -> Dict[str, Any]:
    """Map an oxp-api ``SpanMetadataItem`` to the raw ClickHouse-shaped span
    dict ``norm.ioa_observe`` reads directly (``SpanName``/``SpanAttributes``/
    ``SpanId``/``ParentSpanId``/``Timestamp``/``Duration``) -- a straight
    field rename, no reformatting: ``SpanMetadataItem`` is itself sourced
    from the same ``otel_traces`` ClickHouse columns (see
    ``oxp.query_builders.sessions.session_spans_query``), so ``timestamp``
    is already ClickHouse's native ``Timestamp`` string and ``duration`` is
    already nanoseconds.
    """
    return {
        "SessionId": span.session_id,
        "SpanId": span.span_id,
        "ParentSpanId": span.parent_span_id,
        "SpanName": span.span_name,
        "SpanType": span.span_type,
        "SpanAttributes": span.span_attributes,
        "StatusCode": span.status_code,
        "ServiceName": span.service_name,
        "Timestamp": span.timestamp,
        "Duration": span.duration,
        "Links.TraceId": span.links_trace_id,
        "Links.SpanId": span.links_span_id,
        "Links.TraceState": span.links_trace_state,
        "Links.Attributes": span.links_attributes,
    }


class NormWrapper:
    """Fetches raw spans via oxp-api and delegates normalization to norm.

    Pipeline: oxp-api -> SpanMetadataItem rows -> raw ClickHouse-shaped span
    dicts -> norm.normalize -> Neo4j.

    All span normalization -- the full handler/heuristic pipeline turning
    spans into KG nodes/edges -- lives in ``norm``. This class is only
    responsible for fetching spans, adapting their shape, and the Neo4j push
    (plus an optional JSON copy of the KG).

    When ``kg_output`` is set, the KG is written as JSON to that path.
    """

    def __init__(
        self,
        db_handler: NormDALHandler,
        debug: bool = False,
        override: bool = False,
        kg_output: Optional[str] = None,
    ):
        self.db_handler = db_handler
        self.debug = debug
        self.override = override
        self.kg_output = kg_output

    def retrieve_and_normalize(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Fetch raw spans via oxp-api and normalize them to KG nodes/edges.

        Returns a dict with ``nodes``, ``edges`` and ``run_id``, or None if
        span fetching or normalization itself failed.
        """
        spans = self._fetch_spans(session_id)
        if spans is None:
            return None

        raw_spans = [_to_otel_span_dict(span) for span in spans]

        if self.debug:
            _dump_jsonl(raw_spans, f"/tmp/norm_worker_spans_{session_id}.jsonl")

        nodes, edges = normalize(raw_spans)
        return {"nodes": nodes, "edges": edges, "run_id": session_id}

    def _fetch_spans(self, session_id: str) -> Optional[List[Any]]:
        """Fetch raw session spans for session_id through oxp-api LocalClient.

        Returns oxp-api's own span model (``SpanMetadataItem``) as-is --
        adapting it to the raw span-dict shape norm expects is
        ``_to_otel_span_dict``'s job, not this method's.
        """
        try:
            db = next(get_db())
            client = OXPLocalClient(db=db)
            response = client.get_session_spans(
                session_ids=[session_id],
                limit=10000,
                order="asc",
            )
            spans = response.spans
        except Exception as exc:
            logger.error("Failed to fetch spans for session_id=%s: %s", session_id, exc)
            return None

        if not spans:
            logger.warning("No spans found for session_id=%s", session_id)
            return None

        logger.info("Fetched %d spans for session_id=%s", len(spans), session_id)
        return spans

    def dump_kg(self, kg: Dict[str, Any], path: str) -> bool:
        """Write the KG (nodes + edges) as JSON to path."""
        nodes = kg["nodes"]
        edges = kg["edges"]
        run_id = kg.get("run_id", "")

        out = {"run_id": run_id, "nodes": nodes, "edges": edges}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2, ensure_ascii=False)

        logger.info("KG written to %s (%d nodes, %d edges)", path, len(nodes), len(edges))
        return True

    def ingest_to_neo4j(self, kg: Dict[str, Any]) -> bool:
        """Push KG to Neo4j, optionally also saving a JSON copy to kg_output."""
        if self.kg_output:
            self.dump_kg(kg, self.kg_output)
        return self._push_to_neo4j(kg)

    def _push_to_neo4j(self, kg: Dict[str, Any]) -> bool:
        """Push KG nodes and edges to Neo4j via oxp-api. Returns True on success.

        norm-worker has no Neo4j connection logic of its own: ``db_handler``
        is built once by ``NormWorker`` (wrapping the same shared connector
        singleton oxp-api's own endpoints use) and injected here - this
        method never builds or closes a connection itself.
        """
        nodes = kg["nodes"]
        edges = kg["edges"]
        run_id = kg.get("run_id", "")

        logger.info("Pushing KG to Neo4j: %d nodes, %d edges", len(nodes), len(edges))

        try:
            result = self.db_handler.ingest_normalized_kg(nodes, edges, run_id, self.override, batch_size=200)
        except Exception as exc:
            logger.error("Neo4j push failed for run_id=%s: %s", run_id, exc)
            return False

        logger.info("Neo4j push complete for run_id=%s", run_id)
        return bool(result)


def _dump_jsonl(records: List[Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
