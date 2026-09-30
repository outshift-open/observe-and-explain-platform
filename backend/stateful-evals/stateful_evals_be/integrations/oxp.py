#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXP span normalization and optional, in-process API-library database access."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any, Protocol

from stateful_evals_be.models.spans import SpanRecord


class SpanMetadata(Protocol):
    def model_dump(self) -> dict[str, Any]: ...


class SpanPage(Protocol):
    @property
    def spans(self) -> Sequence[SpanMetadata]: ...


class SessionSpanClient(Protocol):
    """Minimum query interface; concrete API-library imports remain optional."""

    def get_session_spans(
        self,
        *,
        session_ids: list[str] | None = None,
        limit: int = 500,
        offset: int = 0,
        order: str = "asc",
    ) -> SpanPage: ...


def oxp_span_to_otel(span: dict[str, Any]) -> SpanRecord:
    """Map a OXP SpanMetadataItem to the evaluator's existing OTel format."""
    return {
        "SpanId": span.get("span_id", ""),
        "SpanName": span.get("span_name", ""),
        "SpanAttributes": span.get("span_attributes", {}),
        "StatusCode": span.get("status_code", ""),
        "ServiceName": span.get("service_name", ""),
        "Timestamp": span.get("timestamp", ""),
        "ParentSpanId": span.get("parent_span_id", ""),
        "Duration": span.get("duration", 0),
        "TraceId": span.get("trace_id", ""),
        "Links.TraceId": span.get("links_trace_id", []),
        "Links.SpanId": span.get("links_span_id", []),
        "Links.TraceState": span.get("links_trace_state", []),
        "Links.Attributes": span.get("links_attributes", []),
    }


@contextmanager
def local_api_client(*, persist_metrics: bool = False) -> Iterator[SessionSpanClient]:
    """Create a LocalClient from API-library settings, closing owned connectors.

    Imports stay lazy so file/in-memory evaluation needs no API package or DB.
    Span queries use ClickHouse; optional metric writes use Neo4j, as in the worker.
    Callers with another backend can instead supply their own configured client.
    """
    try:
        from oxp.client.local import LocalClient

        client = LocalClient.from_settings(persist_metrics=persist_metrics)
    except ImportError as exc:
        raise ImportError(
            "Database evaluation requires the oxp-api package and its "
            "dependencies. Install the repository's api package or supply an "
            "api_client; file and in-memory evaluation do not require it."
        ) from exc

    with client:
        yield client


def fetch_session_spans(
    client: SessionSpanClient, session_id: str, *, page_size: int = 500
) -> list[SpanRecord]:
    """Normalize a complete API-library session; never close the supplied client.

    Evaluate completed sessions: offset pagination does not snapshot active traces.
    """
    if not session_id or not session_id.strip():
        raise ValueError("session_id must not be empty")
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    iterator = getattr(client, "iter_session_spans", None)
    if callable(iterator):
        return [
            oxp_span_to_otel(span.model_dump())
            for span in iterator(session_id, page_size=page_size)
        ]

    # Preserve support for existing injected clients exposing only the paged API.
    spans: list[SpanRecord] = []
    offset = 0
    while True:
        response = client.get_session_spans(
            session_ids=[session_id], limit=page_size, offset=offset, order="asc"
        )
        page = response.spans
        spans.extend(oxp_span_to_otel(span.model_dump()) for span in page)
        if len(page) < page_size:
            return spans
        offset += len(page)
