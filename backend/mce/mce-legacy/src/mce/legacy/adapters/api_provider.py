#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import os
import logging
import requests
from typing import Any
from mce.core.provider import DataProvider
from mce.core.metric import MetricRequirements
from datetime import datetime

logger = logging.getLogger(__name__)


class ApiDataProvider(DataProvider):
    """
    Adapter that connects MCE v2 to the legacy Telemetry Hub API.
    Fetches raw OTel spans and normalizes them into MCE v2 session context.
    """

    def __init__(self, base_url: str | None = None):
        self.base_url = base_url or os.environ.get(
            "API_BASE_URL", "http://localhost:8000"
        )
        self.verify_ssl = os.environ.get("API_VERIFY_SSL", "true").lower() == "true"
        self.timeout = int(os.environ.get("API_TIMEOUT", "30"))

    def fetch(
        self, resource_id: str, requirements: MetricRequirements
    ) -> dict[str, Any]:
        """
        Fetch session data and spans from the API.
        """
        logger.info(f"Fetching session {resource_id} from {self.base_url}")

        # 1. Fetch Spans
        spans = self._fetch_session_spans(resource_id)

        # 2. Normalize Spans
        normalized_spans = [self._normalize_span(s) for s in spans]

        # 3. Bucketize Spans (MCE v2 convention)
        tool_spans = [s for s in normalized_spans if s.get("type") == "tool"]
        llm_spans = [s for s in normalized_spans if s.get("type") == "llm"]
        agent_spans = [s for s in normalized_spans if s.get("type") == "agent"]

        # 4. Construct Context
        # Note: Conversation/transcript fetching could be added here if API supports it
        # For now, we reconstruct basic info from spans

        # Build a session-level node so that session metrics (e.g. Duration)
        # can read timing via _detect_resource_type → context["session"].
        # Derive start + duration from the earliest/longest raw span available.
        session_node: dict[str, Any] = {"session_id": resource_id}
        raw_start_ms: float = 0.0
        raw_duration_ms: float = 0.0
        for raw in spans:
            # OTel Duration is in nanoseconds
            otel_duration = raw.get("Duration", 0)
            if isinstance(otel_duration, (int, float)) and otel_duration > 0:
                raw_duration_ms = max(raw_duration_ms, float(otel_duration) / 1_000_000)
            if raw_start_ms == 0.0:
                ts = raw.get("Timestamp")
                if ts:
                    try:
                        dt = datetime.fromisoformat(str(ts).replace(" ", "T"))
                        raw_start_ms = dt.timestamp() * 1000
                    except Exception:
                        pass
        if raw_start_ms > 0:
            session_node["startTime"] = raw_start_ms
        if raw_duration_ms > 0:
            session_node["duration"] = raw_duration_ms

        context = {
            "session_id": resource_id,
            "session": session_node,
            "spans": normalized_spans,
            "tool_spans": tool_spans,
            "llm_spans": llm_spans,
            "agent_spans": agent_spans,
            # Basic fallback for conversation if not explicitly fetched
            "conversation_text": "",
            "input_text": "",
            "output_text": "",
        }

        return context

    def _fetch_session_spans(self, session_id: str) -> list[dict[str, Any]]:
        """
        Call /traces/sessions/spans endpoint.
        """
        endpoint = "/traces/sessions/spans"
        url = f"{self.base_url.rstrip('/')}{endpoint}"

        try:
            resp = requests.get(
                url,
                params={"session_ids": session_id},
                verify=self.verify_ssl,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()

            # Response structure: {"data": {"session_id": [spans...]}, "notfound_session_ids": []}
            session_data = data.get("data", {})
            if session_id not in session_data:
                logger.warning(f"Session {session_id} not found in API response.")
                return []

            return session_data[session_id] or []

        except Exception as e:
            logger.error(f"Failed to fetch spans for session {session_id}: {e}")
            raise LookupError(f"Failed to fetch session {session_id}") from e

    def _normalize_span(self, raw_span: dict[str, Any]) -> dict[str, Any]:
        """
        Convert Raw OTel Span (JSON) to MCE v2 Span Dict.
        """
        attributes = raw_span.get("SpanAttributes", {})

        # 1. Determine Type
        # V1 logic: attributes.get("traceloop.span.kind")
        span_kind = attributes.get("traceloop.span.kind", "unknown")

        # 2. Status
        # V1: StatusCode "Error" or "STATUS_CODE_ERROR" -> 2
        raw_status = raw_span.get("StatusCode", "Unset")
        if raw_status in ["Error", "STATUS_CODE_ERROR"]:
            status_code = "ERROR"
        else:
            status_code = "OK"

        # 3. Error Message
        error_msg = raw_span.get("StatusMessage")

        # 4. Timestamps
        try:
            ts_str = raw_span.get("Timestamp")
            # Usually ISO format '2025-06-20 21:37:08.604225'
            # MCE v2 metrics often don't strictly require parsed datetime, but useful
            start_time = ts_str  # Keep raw string or parse if needed
        except (KeyError, AttributeError) as e:
            logger.debug(f"Could not parse timestamp from span: {e}")
            start_time = None

        return {
            "span_id": raw_span.get("SpanId"),
            "name": raw_span.get("SpanName"),
            "type": span_kind,  # "tool", "llm", "agent"
            "status_code": status_code,
            "error": error_msg,
            "start_time": start_time,
            "attributes": attributes,
            "raw": raw_span,
        }
