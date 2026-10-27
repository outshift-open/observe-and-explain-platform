#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Session-related private implementations for :class:`UIClient`."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from oxp.client.constants import (
    COST_PER_TOKEN,
    ERROR_STATUS,
    INPUT_TOKENS_KEY,
    OUTPUT_TOKENS_KEY,
)
from oxp.client.utils import (
    extract_agent_description,
    parse_span_attributes,
    parse_time_filters,
    remove_quotes,
    safe_int,
)
from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    AgentConversationMessage,
    AgentConversationResponse,
    AgentDetailsItem,
    AgentDetailsResponse,
    AgentSubCallMessage,
    Filters,
    GraphEdge,
    GraphNode,
    GraphResponse,
    ImpactAssementAgentItem,
    ImpactAssessmentMetric,
    ImpactAssessmentResponse,
    LatentSpaceEdge,
    LatentSpaceNode,
    LatentSpaceResponse,
    LlmCallGraphNodeData,
    SingleValueData,
    SpanAttribute,
    ToolCallGraphNodeData,
    TraceItem,
    TracesResponse,
    TrajectoryResponse,
    UniqueAgentPerSession,
    WaterfallResponse,
    WaterfallSpan,
)
from oxp.query_builders import ui as ui_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)

_TIME_ONLY_TIMESTAMP_RE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?$")
_ROOT_DURATION_EXCLUDED_SPAN_NAMES = {"session.end"}


def _parse_trace_timestamp(value: object) -> datetime | None:
    """Parse the timestamp formats returned by the configured backends."""
    if isinstance(value, datetime):
        return value

    raw_value = remove_quotes(str(value)).strip() if value is not None else ""
    if not raw_value:
        return None

    normalized = raw_value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%M:%S.%f",
        "%M:%S",
        "%H:%M:%S.%f",
        "%H:%M:%S",
        "%H:%M",
    ):
        try:
            parsed = datetime.strptime(raw_value, fmt)
        except ValueError:
            continue

        if fmt in {"%M:%S.%f", "%M:%S", "%H:%M:%S.%f", "%H:%M:%S", "%H:%M"}:
            return parsed.replace(year=1970, month=1, day=1)
        return parsed

    return None


def _format_trace_timestamp(value: datetime | None, *, template: str = "") -> str:
    """Format a timestamp using the same shape as the source value when possible."""
    if value is None:
        return template

    raw_template = remove_quotes(template).strip()
    if _TIME_ONLY_TIMESTAMP_RE.match(raw_template):
        if raw_template.count(":") == 1:
            return value.strftime("%M:%S.%f").rstrip("0").rstrip(".")
        if "." in raw_template:
            return value.strftime("%H:%M:%S.%f").rstrip("0").rstrip(".")
        return value.strftime("%H:%M:%S")

    return value.isoformat()


def _duration_in_ms(
    start_time: datetime | None,
    end_time: datetime | None,
    fallback: int = 0,
) -> int:
    if start_time is None or end_time is None:
        return max(fallback, 0)
    return max(int((end_time - start_time).total_seconds() * 1000), 0)


def _include_in_root_duration(span_name: str) -> bool:
    return span_name not in _ROOT_DURATION_EXCLUDED_SPAN_NAMES


def _fetch_state_machine_graph(
    db: Connector,
    *,
    session_id: str,
    level: Optional[str] = None,
) -> GraphResponse:
    """Fetch the execution graph for a session via the configured connector."""
    query, params = ui_queries.state_machine_graph_query(
        session_id=session_id,
        level=level,
    )

    try:
        records = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(f"Failed to fetch state machine graph: {exc}") from exc

    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    added_nodes: set[str] = set()
    node_levels: dict[str, set[str]] = {}

    for record in records:
        if not isinstance(record, dict):
            continue

        from_state_id = str(record.get("fromStateId") or "")
        to_state_id = str(record.get("toStateId") or "")
        hierarchy_level = record.get("hierarchyLevel")

        if not from_state_id:
            continue

        if from_state_id not in node_levels:
            node_levels[from_state_id] = set()
        if hierarchy_level:
            node_levels[from_state_id].add(str(hierarchy_level))

        if to_state_id:
            if to_state_id not in node_levels:
                node_levels[to_state_id] = set()
            if hierarchy_level:
                node_levels[to_state_id].add(str(hierarchy_level))

        if from_state_id not in added_nodes:
            from_type = str(record.get("fromType") or "intermediate")
            nodes.append(
                GraphNode(
                    id=from_state_id,
                    label=from_state_id[:30],
                    type="state",
                    data={
                        "state_id": from_state_id,
                        "content": record.get("fromContent"),
                        "semantic_type": from_type,
                        "path": record.get("fromPath"),
                    },
                    metadata={},
                )
            )
            added_nodes.add(from_state_id)

        if to_state_id and to_state_id not in added_nodes:
            to_type = str(record.get("toType") or "intermediate")
            nodes.append(
                GraphNode(
                    id=to_state_id,
                    label=to_state_id[:30],
                    type="state",
                    data={
                        "state_id": to_state_id,
                        "content": record.get("toContent"),
                        "semantic_type": to_type,
                        "path": record.get("toPath"),
                    },
                    metadata={},
                )
            )
            added_nodes.add(to_state_id)

        if to_state_id:
            entity_name = str(record.get("entityName") or "unknown")
            entity_type = str(record.get("entityType") or "unknown")
            edge_data: dict[str, Any] = {
                "transition_id": record.get("transitionId"),
                "duration": record.get("duration"),
                "edge_type": record.get("edgeType"),
                "entity_name": entity_name,
                "entity_type": entity_type,
            }
            span_id = record.get("spanId")
            if span_id:
                edge_data["spanId"] = span_id

            execution_id = record.get("executionId")
            if execution_id:
                edge_data["executionId"] = execution_id
            call_type = record.get("callType")
            if call_type:
                edge_data["call_type"] = call_type
            edges.append(
                GraphEdge(
                    id=str(
                        record.get("transitionId") or f"{from_state_id}->{to_state_id}"
                    ),
                    source=from_state_id,
                    target=to_state_id,
                    label=entity_name,
                    type="transition",
                    data=edge_data,
                    metadata={"hierarchy_level": hierarchy_level},
                )
            )

    level_order = {"session": 0, "mas": 1, "agent": 2, "task": 3, "call": 4}
    for node in nodes:
        if node.id in node_levels and node_levels[node.id]:
            levels = sorted(
                node_levels[node.id], key=lambda item: level_order.get(item, 99)
            )
            if node.metadata is None:
                node.metadata = {}
            node.metadata["hierarchy_levels"] = levels

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        session_id=session_id,
        hierarchy_level=level,
        metadata={
            "graph_type": "state_machine",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "source": "neo4j",
        },
    )


# ── get_sessions ─────────────────────────────────────────────────────────────


def _get_sessions(
    db: Connector,
    dialect: Dialect,
    *,
    app_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> TracesResponse:
    """Get list of session (trace) summaries.

    Filters by optional app_name and time range. Returns session metadata
    including start_time, end_time, and span_count.
    """
    stmt = ui_queries.sessions_query(
        dialect,
        start_time=start_time,
        end_time=end_time,
        app_name=app_name,
        limit=limit,
        offset=offset,
    )

    try:
        rows = db.execute(stmt)
        sessions = [
            TraceItem(
                session_id=str(r[0]),
                application_id=str(r[1]),
                start_time=str(r[2]),
                end_time=str(r[3]),
            )
            for r in rows
        ]
        return TracesResponse(sessions=sessions)
    except Exception as exc:
        raise DatabaseError(f"Failed to get sessions: {exc}") from exc


# ── get_session_agents ───────────────────────────────────────────────────────


def _get_session_agents(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[UniqueAgentPerSession]:
    filters = Filters(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    start_dt, end_dt = parse_time_filters(filters)

    stmt = ui_queries.session_agents_query(
        dialect,
        session_id=session_id,
        start_time=start_dt,
        end_time=end_dt,
        limit=filters.limit,
        offset=filters.offset,
    )

    try:
        rows = db.execute(stmt)
        return [
            UniqueAgentPerSession(
                agent_id=str(r[0]),
                session_id=str(r[1]),
            )
            for r in rows
        ]
    except Exception as exc:
        raise DatabaseError(f"Failed to get session agents: {exc}") from exc


# ── get_session_agent_details ────────────────────────────────────────────────


def _get_session_agent_details(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
    agent_id: str,
) -> AgentDetailsResponse:
    """Return detailed information about an agent in a session."""

    # 1. Get agent description from agent_start_event rows
    desc_stmt = ui_queries.agent_description_query(
        dialect,
        session_id=session_id,
        agent_id=agent_id,
    )
    try:
        desc_rows = db.execute(desc_stmt)
        description = extract_agent_description(desc_rows, agent_id)
    except Exception as exc:
        logger.error("malformed or unexpected data (description): %s", exc)
        description = ""

    # 2. Get agent spans (for chat.input / chat.output attributes)
    spans_stmt = ui_queries.agent_spans_query(
        dialect,
        session_id=session_id,
        agent_id=agent_id,
    )
    try:
        db.execute(spans_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data (spans): %s", exc)

    attributes: list[SpanAttribute] = []
    # TODO: Add chat input and output attributes (gen_ai.completion.*.content and gen_ai.prompt.*.content) for chat spans

    # 3. Aggregate token counts and collect LLM names from chat spans
    token_stmt = ui_queries.agent_token_aggregates_query(
        dialect,
        session_id=session_id,
        agent_id=agent_id,
    )
    try:
        token_rows = db.execute(token_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data (tokens): %s", exc)
        token_rows = []

    total_input_tokens = 0
    total_output_tokens = 0
    llm_names: list[str] = []

    for row in token_rows:
        attrs = parse_span_attributes(str(row[0]) if row[0] else "")
        total_input_tokens += safe_int(attrs.get(INPUT_TOKENS_KEY, ""))
        total_output_tokens += safe_int(attrs.get(OUTPUT_TOKENS_KEY, ""))
        model_name = attrs.get("gen_ai.request.model", "")
        if model_name and model_name not in llm_names:
            llm_names.append(model_name)

    return AgentDetailsResponse(
        agentDetails=AgentDetailsItem(
            id=session_id,
            name=agent_id,
            description=description,
            llms=llm_names,
            inputTokens=SingleValueData(
                value=float(total_input_tokens),
                unit="SCALAR",
            ),
            outputTokens=SingleValueData(
                value=float(total_output_tokens),
                unit="SCALAR",
            ),
            inputCost=SingleValueData(
                value=float(total_input_tokens) * COST_PER_TOKEN,
                unit="DOLLAR",
            ),
            outputCost=SingleValueData(
                value=float(total_output_tokens) * COST_PER_TOKEN,
                unit="DOLLAR",
            ),
            attributes=attributes,
        )
    )


def _get_session_impact_assessment(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
) -> ImpactAssessmentResponse:
    """Return impact assessment for a session."""
    stmt = ui_queries.session_impact_assessment_query(
        dialect,
        session_id=session_id,
    )
    try:
        rows = db.execute(stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get impact assessment for session '{session_id}': {exc}"
        ) from exc

    if not rows:
        return ImpactAssessmentResponse()

    report = []
    for row in rows:
        metric_name = str(row.get("metricName") or "")
        contrib_raw = str(row.get("contributions") or "")
        try:
            contrib = json.loads(contrib_raw)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse contribution JSON: %s", exc)
            continue
        agents_list = []
        for agent in contrib.keys():
            value = contrib[agent]
            agents_list.append(
                ImpactAssementAgentItem(
                    agent_name=agent,
                    value=SingleValueData(value=value, unit="PERCENTAGE"),
                )
            )
        report.append(
            ImpactAssessmentMetric(
                metric_name=metric_name,
                agents=agents_list,
            )
        )
    # Process rows to build the impact assessment response
    # TODO: Implement the actual processing logic

    return ImpactAssessmentResponse(impact_report=report)


# ── _get_session_timeline ───────────────────────────────────────────────


def _get_children_spans(
    parent_id: str,
    parent_child_map: dict[str, list[dict]],
    used_node_map: dict[str, bool],
) -> tuple[list[WaterfallSpan], datetime | None, datetime | None]:
    """Recursively build child spans for a given parent.

    Returns ``(children, min_start_time, max_end_time)`` where the
    timestamps are normalized ``datetime`` objects.
    """
    children_data = parent_child_map.get(parent_id, [])
    if not children_data:
        return [], None, None

    result_children: list[WaterfallSpan] = []
    overall_min_start: datetime | None = None
    overall_max_end: datetime | None = None

    for child in children_data:
        span_id = child["span_id"]
        used_node_map[span_id] = True

        span_name = child.get("span_name", "")
        icon = span_name.rsplit(".", 1)[-1] if "." in span_name else span_name

        start_time_str = child.get("start_time", "")
        end_time_str = child.get("end_time", "")
        start_time_dt = child.get("start_time_dt")
        end_time_dt = child.get("end_time_dt")

        # Recurse into grandchildren
        grand_children, gc_min, gc_max = _get_children_spans(
            span_id,
            parent_child_map,
            used_node_map,
        )

        # If grandchildren provide tighter bounds, widen
        if gc_min and (start_time_dt is None or gc_min < start_time_dt):
            start_time_dt = gc_min
        if gc_max and (end_time_dt is None or gc_max > end_time_dt):
            end_time_dt = gc_max

        start_time_str = _format_trace_timestamp(start_time_dt, template=start_time_str)
        end_time_str = _format_trace_timestamp(end_time_dt, template=end_time_str)
        duration_val = _duration_in_ms(
            start_time_dt,
            end_time_dt,
            child.get("duration", 0),
        )

        span = WaterfallSpan(
            spanId=span_id,
            duration=max(duration_val, 0),
            spanName=span_name,
            timestamp=start_time_str,
            startTime=start_time_str,
            endTime=end_time_str,
            icon=icon,
            error=(child.get("status_code", "") == ERROR_STATUS),
            childrenSpans=grand_children,
        )
        result_children.append(span)

        if start_time_dt and (
            overall_min_start is None or start_time_dt < overall_min_start
        ):
            overall_min_start = start_time_dt
        if end_time_dt and (overall_max_end is None or end_time_dt > overall_max_end):
            overall_max_end = end_time_dt

    return result_children, overall_min_start, overall_max_end


def _get_session_timeline_waterfall(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
) -> WaterfallResponse:
    """Build a waterfall span tree for a session.

    Two code paths:
    - **LangGraph** apps (application_id is ``"Miss-Marple"`` or starts
      with ``"xmas-"``): the root is the LangGraph span itself, children
      get ``"task"`` icons.
    - **Normal** apps: a synthetic ``"root"`` node wraps agent-level
      children (``"agent"`` icon); orphaned spans are attached to the
      root as well.
    """
    stmt = ui_queries.traces_by_session_id_query(
        dialect,
        session_id=session_id,
    )
    try:
        rows = db.execute(stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to build waterfall for session '{session_id}': {exc}"
        ) from exc

    if not rows:
        return WaterfallResponse()

    # Parse rows into span dicts and build parent→children map
    spans: list[dict] = []
    parent_child_map: dict[str, list[dict]] = {}

    for row in rows:
        ts_str = str(row[0]) if row[0] else ""
        span_id = str(row[1]) if row[1] else ""
        span_name = str(row[2]) if row[2] else ""
        parent_span_id = str(row[3]) if row[3] else ""
        agent_id = str(row[4]) if row[4] else ""
        application_id = str(row[5]) if row[5] else ""
        duration_ns = int(row[6]) if row[6] else 0
        status_code = str(row[7]) if row[7] else ""

        # Convert nanoseconds → milliseconds
        duration_ms = duration_ns // 1_000_000

        # Derive start/end from timestamp + duration
        start_dt = _parse_trace_timestamp(ts_str)

        if start_dt:
            end_dt = start_dt + timedelta(milliseconds=duration_ms)
            start_iso = _format_trace_timestamp(start_dt, template=ts_str)
            end_iso = _format_trace_timestamp(end_dt, template=ts_str)
        else:
            end_dt = None
            start_iso = ts_str
            end_iso = ts_str

        span_dict = {
            "span_id": span_id,
            "span_name": span_name,
            "parent_span_id": parent_span_id,
            "agent_id": agent_id,
            "application_id": application_id,
            "duration": duration_ms,
            "start_time": start_iso,
            "end_time": end_iso,
            "start_time_dt": start_dt,
            "end_time_dt": end_dt,
            "status_code": status_code,
        }
        spans.append(span_dict)

        if parent_span_id:
            parent_child_map.setdefault(parent_span_id, []).append(span_dict)

    # Determine if LangGraph app
    first_app_id = spans[0]["application_id"] if spans else ""
    is_langgraph = first_app_id == "Miss-Marple" or first_app_id.startswith("xmas-")

    used_node_map: dict[str, bool] = {}

    if is_langgraph:
        # Find the LangGraph root span (one whose parent is empty or not in our set)
        span_id_set = {s["span_id"] for s in spans}
        lg_root = None
        for s in spans:
            if not s["parent_span_id"] or s["parent_span_id"] not in span_id_set:
                lg_root = s
                break

        if not lg_root:
            lg_root = spans[0]

        used_node_map[lg_root["span_id"]] = True

        children, c_min, c_max = _get_children_spans(
            lg_root["span_id"],
            parent_child_map,
            used_node_map,
        )

        # Override children icons to "task"
        for child in children:
            child.icon = "task"

        root_start_dt = lg_root["start_time_dt"]
        root_end_dt = lg_root["end_time_dt"]
        if c_min and (root_start_dt is None or c_min < root_start_dt):
            root_start_dt = c_min
        if c_max and (root_end_dt is None or c_max > root_end_dt):
            root_end_dt = c_max

        root_start = _format_trace_timestamp(
            root_start_dt, template=lg_root["start_time"]
        )
        root_end = _format_trace_timestamp(root_end_dt, template=lg_root["end_time"])
        root_duration = _duration_in_ms(
            root_start_dt,
            root_end_dt,
            lg_root["duration"],
        )

        return WaterfallResponse(
            spanId=lg_root["span_id"],
            timestamp=root_start,
            startTime=root_start,
            spanName=lg_root["span_name"],
            icon="application",
            endTime=root_end,
            duration=max(root_duration, 0),
            error=(lg_root["status_code"] == ERROR_STATUS),
            Spans=children,
        )
    else:
        # Normal apps: build a synthetic root
        SKIP_NAMES = {"session.publish", "special_agent"}

        # First pass: find root-level children (agents)
        root_children: list[WaterfallSpan] = []
        overall_min: datetime | None = None
        overall_max: datetime | None = None
        fallback_min: datetime | None = None
        fallback_max: datetime | None = None
        root_start_template = ""
        root_end_template = ""
        fallback_start_template = ""
        fallback_end_template = ""

        span_id_set = {s["span_id"] for s in spans}
        for s in spans:
            span_name = s["span_name"]
            # Skip filtered names
            last_part = span_name.rsplit(".", 1)[-1] if "." in span_name else span_name
            if last_part in SKIP_NAMES:
                used_node_map[s["span_id"]] = True
                continue

            # Root-level: no parent or parent not in our set
            if not s["parent_span_id"] or s["parent_span_id"] not in span_id_set:
                used_node_map[s["span_id"]] = True

                children, c_min, c_max = _get_children_spans(
                    s["span_id"],
                    parent_child_map,
                    used_node_map,
                )

                start_dt = s["start_time_dt"]
                end_dt = s["end_time_dt"]

                if c_min and (start_dt is None or c_min < start_dt):
                    start_dt = c_min
                if c_max and (end_dt is None or c_max > end_dt):
                    end_dt = c_max

                start_t = _format_trace_timestamp(start_dt, template=s["start_time"])
                end_t = _format_trace_timestamp(end_dt, template=s["end_time"])
                dur = _duration_in_ms(start_dt, end_dt, s["duration"])

                root_children.append(
                    WaterfallSpan(
                        spanId=s["span_id"],
                        duration=max(dur, 0),
                        spanName=span_name,
                        timestamp=start_t,
                        startTime=start_t,
                        endTime=end_t,
                        icon="agent",
                        error=(s["status_code"] == ERROR_STATUS),
                        childrenSpans=children,
                    )
                )

                if start_dt and (fallback_min is None or start_dt < fallback_min):
                    fallback_min = start_dt
                    fallback_start_template = start_t
                if end_dt and (fallback_max is None or end_dt > fallback_max):
                    fallback_max = end_dt
                    fallback_end_template = end_t

                if _include_in_root_duration(span_name):
                    if start_dt and (overall_min is None or start_dt < overall_min):
                        overall_min = start_dt
                        root_start_template = start_t
                    if end_dt and (overall_max is None or end_dt > overall_max):
                        overall_max = end_dt
                        root_end_template = end_t

        # Second pass: orphaned spans not yet used
        for s in spans:
            if s["span_id"] in used_node_map:
                continue
            span_name = s["span_name"]
            last_part = span_name.rsplit(".", 1)[-1] if "." in span_name else span_name
            if last_part in SKIP_NAMES:
                continue

            used_node_map[s["span_id"]] = True

            children, c_min, c_max = _get_children_spans(
                s["span_id"],
                parent_child_map,
                used_node_map,
            )

            start_dt = s["start_time_dt"]
            end_dt = s["end_time_dt"]

            if c_min and (start_dt is None or c_min < start_dt):
                start_dt = c_min
            if c_max and (end_dt is None or c_max > end_dt):
                end_dt = c_max

            start_t = _format_trace_timestamp(start_dt, template=s["start_time"])
            end_t = _format_trace_timestamp(end_dt, template=s["end_time"])
            dur = _duration_in_ms(start_dt, end_dt, s["duration"])

            icon = last_part
            root_children.append(
                WaterfallSpan(
                    spanId=s["span_id"],
                    duration=max(dur, 0),
                    spanName=span_name,
                    timestamp=start_t,
                    startTime=start_t,
                    endTime=end_t,
                    icon=icon,
                    error=(s["status_code"] == ERROR_STATUS),
                    childrenSpans=children,
                )
            )

            if start_dt and (fallback_min is None or start_dt < fallback_min):
                fallback_min = start_dt
                fallback_start_template = start_t
            if end_dt and (fallback_max is None or end_dt > fallback_max):
                fallback_max = end_dt
                fallback_end_template = end_t

            if _include_in_root_duration(span_name):
                if start_dt and (overall_min is None or start_dt < overall_min):
                    overall_min = start_dt
                    root_start_template = start_t
                if end_dt and (overall_max is None or end_dt > overall_max):
                    overall_max = end_dt
                    root_end_template = end_t

        if overall_min is None:
            overall_min = fallback_min
            root_start_template = fallback_start_template
        if overall_max is None:
            overall_max = fallback_max
            root_end_template = fallback_end_template

        # Compute root duration
        root_duration = _duration_in_ms(overall_min, overall_max)
        root_start = _format_trace_timestamp(overall_min, template=root_start_template)
        root_end = _format_trace_timestamp(overall_max, template=root_end_template)

        return WaterfallResponse(
            spanId="root",
            timestamp=root_start,
            startTime=root_start,
            spanName="root",
            icon="application",
            endTime=root_end,
            duration=max(root_duration, 0),
            error=False,
            Spans=root_children,
        )


def _get_session_timeline(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
    level: Optional[str] = None,
) -> GraphResponse:
    return _fetch_state_machine_graph(
        db,
        session_id=session_id,
        level=level,
    )


def _get_session_trajectory(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
) -> TrajectoryResponse:
    return TrajectoryResponse(info="Trajectory data not implemented yet.")


def _fetch_execution_hierarchy_records(
    db: Connector,
    *,
    session_id: str,
    query_builder: Callable[..., tuple[str, dict[str, Any]]],
    scope: str,
) -> list[dict[str, Any]]:
    query, params = query_builder(session_id=session_id)
    try:
        records = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to fetch execution hierarchy graph ({scope}): {exc}"
        ) from exc

    return [record for record in records if isinstance(record, dict)]


def _execution_timestamp_sort_key(value: object) -> tuple[int, object]:
    if isinstance(value, datetime):
        return (0, value)
    if isinstance(value, (int, float)):
        return (1, float(value))
    if isinstance(value, str):
        parsed = _parse_trace_timestamp(value)
        if parsed is not None:
            return (0, parsed)
        return (2, value)
    if value is None:
        return (4, "")
    return (3, str(value))


def _sorted_node_refs(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        nodes, key=lambda item: _execution_timestamp_sort_key(item.get("timestamp"))
    )


def _append_sequence_edges(edges: list[GraphEdge], nodes: list[dict[str, Any]]) -> None:
    sorted_nodes = _sorted_node_refs(nodes)
    for i in range(len(sorted_nodes) - 1):
        from_node = str(sorted_nodes[i]["id"])
        to_node = str(sorted_nodes[i + 1]["id"])
        edges.append(
            GraphEdge(
                id=f"seq_{from_node}_to_{to_node}",
                source=from_node,
                target=to_node,
                label="",
                type="sequence",
                data={"relationship": "followed_by"},
                metadata={},
            )
        )


def _find_parent_node_id(
    candidates: list[dict[str, Any]],
    timestamp: object,
) -> str | None:
    if not candidates:
        return None

    target_key = _execution_timestamp_sort_key(timestamp)
    sorted_candidates = _sorted_node_refs(candidates)
    for candidate in reversed(sorted_candidates):
        if _execution_timestamp_sort_key(candidate.get("timestamp")) <= target_key:
            return str(candidate["id"])
    return str(sorted_candidates[0]["id"])


def _parse_json_value(value: object) -> object:
    if not value:
        return None
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return value


def _append_hierarchy_edges(
    edges: list[GraphEdge],
    hierarchy_edges: list[dict[str, Any]],
) -> None:
    sorted_hierarchy = sorted(
        hierarchy_edges,
        key=lambda item: (
            int(item.get("level", 99)),
            _execution_timestamp_sort_key(item.get("timestamp")),
        ),
    )
    for seq_num, edge_data in enumerate(sorted_hierarchy, start=1):
        edges.append(
            GraphEdge(
                id=str(edge_data["id"]),
                source=str(edge_data["source"]),
                target=str(edge_data["target"]),
                label=str(seq_num),
                type="hierarchy",
                data={"relationship": "contains", "sequence": seq_num},
                metadata={},
            )
        )


def fetch_execution_hierarchy_graph(
    db: Connector,
    *,
    session_id: str,
) -> GraphResponse:
    """Fetch hierarchical execution graph for a session via the configured connector."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_ids: set[str] = set()
    mas_nodes: list[dict[str, Any]] = []
    agent_nodes: list[dict[str, Any]] = []
    call_nodes: list[dict[str, Any]] = []
    hierarchy_edges: list[dict[str, Any]] = []

    session_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_session_state_query,
        scope="session",
    )
    mas_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_mas_query,
        scope="mas",
    )
    agent_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_agent_query,
        scope="agent",
    )
    tool_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_tool_call_query,
        scope="tool_call",
    )
    llm_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_llm_call_query,
        scope="llm_call",
    )

    session_node_id = f"session-{session_id}"
    first_session_record = session_records[0] if session_records else {}
    session_input = first_session_record.get("inputContent")
    session_output = first_session_record.get("outputContent")

    nodes.append(
        GraphNode(
            id=session_node_id,
            label="Session",
            type="session",
            data={
                "session_id": session_id,
                "level": "session",
                "input": session_input,
                "output": session_output,
            },
            metadata={},
        )
    )
    node_ids.add(session_node_id)

    for record in mas_records:
        transition_id = str(record.get("transitionId") or "")
        if not transition_id or transition_id in node_ids:
            continue

        timestamp = record.get("timestamp") or 0
        duration = record.get("duration") or 0
        edge_type = str(record.get("edgeType") or "")
        is_hitl = "hitl" in edge_type.lower() or "human" in edge_type.lower()

        nodes.append(
            GraphNode(
                id=transition_id,
                label="HITL" if is_hitl else "MAS Call",
                type="mas",
                data={
                    "transition_id": transition_id,
                    "level": "mas",
                    "duration": duration,
                    "edge_type": edge_type,
                    "timestamp": timestamp,
                    "is_hitl": is_hitl,
                    "input": record.get("inputContent"),
                    "output": record.get("outputContent"),
                },
                metadata={},
            )
        )
        node_ids.add(transition_id)
        mas_nodes.append({"id": transition_id, "timestamp": timestamp})
        hierarchy_edges.append(
            {
                "id": f"{session_node_id}_to_{transition_id}",
                "source": session_node_id,
                "target": transition_id,
                "level": 1,
                "timestamp": timestamp,
            }
        )

    _append_sequence_edges(edges, mas_nodes)

    for record in agent_records:
        transition_id = str(record.get("transitionId") or "")
        if not transition_id or transition_id in node_ids:
            continue

        timestamp = record.get("timestamp") or 0
        duration = record.get("duration") or 0
        edge_type = str(record.get("edgeType") or "")
        agent_name = str(record.get("agentName") or "Agent")
        execution_id = record.get("executionId")

        nodes.append(
            GraphNode(
                id=transition_id,
                label=f"{agent_name} Call" if agent_name else "Agent Call",
                type="agent",
                data={
                    "transition_id": transition_id,
                    "level": "agent",
                    "agent_name": agent_name,
                    "duration": duration,
                    "edge_type": edge_type,
                    "timestamp": timestamp,
                    "execution_id": execution_id,
                    "input": record.get("inputContent"),
                    "output": record.get("outputContent"),
                },
                metadata={},
            )
        )
        node_ids.add(transition_id)
        agent_nodes.append({"id": transition_id, "timestamp": timestamp})

        parent_mas_id = _find_parent_node_id(mas_nodes, timestamp)
        if parent_mas_id:
            hierarchy_edges.append(
                {
                    "id": f"{parent_mas_id}_to_{transition_id}",
                    "source": parent_mas_id,
                    "target": transition_id,
                    "level": 2,
                    "timestamp": timestamp,
                }
            )

    _append_sequence_edges(edges, agent_nodes)

    agent_exec_to_transition_id: dict[str, str] = {}
    for record in agent_records:
        execution_id = record.get("executionId")
        transition_id = record.get("transitionId")
        if execution_id and transition_id:
            agent_exec_to_transition_id[str(execution_id)] = str(transition_id)

    for record in tool_records:
        transition_id = str(record.get("transitionId") or "")
        if not transition_id or transition_id in node_ids:
            continue

        timestamp = record.get("timestamp") or 0
        duration = record.get("duration") or 0
        edge_type = str(record.get("edgeType") or "")
        tool_name = record.get("toolName")
        execution_id = record.get("executionId")
        parent_agent_exec_id = record.get("parentAgentExecId")

        nodes.append(
            GraphNode(
                id=transition_id,
                label=str(tool_name) if tool_name else "Tool Call",
                type="call",
                data=ToolCallGraphNodeData(
                    transition_id=transition_id,
                    level="call",
                    call_type="tool",
                    tool_name=str(tool_name) if tool_name is not None else None,
                    duration=int(duration) if duration is not None else 0,
                    edge_type=edge_type,
                    timestamp=timestamp,
                    execution_id=str(execution_id)
                    if execution_id is not None
                    else None,
                    input_params=_parse_json_value(record.get("inputParams")),
                    input=str(record.get("inputContent"))
                    if record.get("inputContent") is not None
                    else None,
                    output=str(record.get("outputContent"))
                    if record.get("outputContent") is not None
                    else None,
                    parent_agent_exec_id=(
                        str(parent_agent_exec_id)
                        if parent_agent_exec_id is not None
                        else None
                    ),
                ).model_dump(),
                metadata={},
            )
        )
        node_ids.add(transition_id)
        call_nodes.append({"id": transition_id, "timestamp": timestamp})

        if parent_agent_exec_id:
            parent_agent_id = agent_exec_to_transition_id.get(str(parent_agent_exec_id))
            if parent_agent_id:
                hierarchy_edges.append(
                    {
                        "id": f"{parent_agent_id}_to_{transition_id}",
                        "source": parent_agent_id,
                        "target": transition_id,
                        "level": 3,
                        "timestamp": timestamp,
                    }
                )

    for record in llm_records:
        transition_id = str(record.get("transitionId") or "")
        if not transition_id or transition_id in node_ids:
            continue

        timestamp = record.get("timestamp") or 0
        model_name = record.get("modelName")
        parent_agent_exec_id = record.get("parentAgentExecId")

        nodes.append(
            GraphNode(
                id=transition_id,
                label=f"LLM: {model_name}" if model_name else "LLM Call",
                type="call",
                data=LlmCallGraphNodeData(
                    transition_id=transition_id,
                    level="call",
                    call_type="llm",
                    model_name=str(model_name) if model_name is not None else None,
                    provider=(
                        str(record.get("provider"))
                        if record.get("provider") is not None
                        else None
                    ),
                    prompt_tokens=record.get("promptTokens"),
                    completion_tokens=record.get("completionTokens"),
                    total_tokens=record.get("totalTokens"),
                    cache_read_tokens=record.get("cacheReadTokens"),
                    temperature=record.get("temperature"),
                    finish_reason=(
                        str(record.get("finishReason"))
                        if record.get("finishReason") is not None
                        else None
                    ),
                    duration=record.get("duration") or 0,
                    edge_type=str(record.get("edgeType") or ""),
                    timestamp=timestamp,
                    execution_id=(
                        str(record.get("executionId"))
                        if record.get("executionId") is not None
                        else None
                    ),
                    input=(
                        str(record.get("inputContent"))
                        if record.get("inputContent") is not None
                        else None
                    ),
                    output=(
                        str(record.get("outputContent"))
                        if record.get("outputContent") is not None
                        else None
                    ),
                    parent_agent_exec_id=(
                        str(parent_agent_exec_id)
                        if parent_agent_exec_id is not None
                        else None
                    ),
                ).model_dump(),
                metadata={},
            )
        )
        node_ids.add(transition_id)
        call_nodes.append({"id": transition_id, "timestamp": timestamp})

        if parent_agent_exec_id:
            parent_agent_id = agent_exec_to_transition_id.get(str(parent_agent_exec_id))
            if parent_agent_id:
                hierarchy_edges.append(
                    {
                        "id": f"{parent_agent_id}_to_{transition_id}",
                        "source": parent_agent_id,
                        "target": transition_id,
                        "level": 3,
                        "timestamp": timestamp,
                    }
                )

    _append_sequence_edges(edges, call_nodes)
    _append_hierarchy_edges(edges, hierarchy_edges)

    return GraphResponse(
        nodes=nodes,
        edges=edges,
        session_id=session_id,
        metadata={
            "graph_type": "execution_hierarchy",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "levels": {
                "session": 1,
                "mas": len(mas_nodes),
                "agent": len(agent_nodes),
                "call": len(call_nodes),
            },
            "source": "neo4j",
        },
    )


def _get_session_execution_graph(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
) -> GraphResponse:
    return fetch_execution_hierarchy_graph(
        db,
        session_id=session_id,
    )


def fetch_agent_conversation(
    db: Connector,
    *,
    session_id: str,
) -> AgentConversationResponse:
    """Fetch the ordered "conversation" for a session.

    Agent-level turns alone only carry each agent's own routing
    input/output (e.g. a ``Command`` to hand off to another agent) --
    the actual substance of the conversation is each agent's LLM and tool
    calls, so those are nested under the agent turn that made them (via
    the ``hasLLMCall``/``hasToolCall`` edges), interleaved in the
    chronological order they actually happened, rather than listed as
    separate top-level entries.
    """
    agent_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_agent_query,
        scope="agent",
    )
    llm_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_llm_call_query,
        scope="llm_call",
    )
    tool_records = _fetch_execution_hierarchy_records(
        db,
        session_id=session_id,
        query_builder=ui_queries.execution_hierarchy_tool_call_query,
        scope="tool_call",
    )

    messages: list[AgentConversationMessage] = []
    messages_by_agent_exec_id: dict[str, AgentConversationMessage] = {}
    seen_transition_ids: set[str] = set()

    for record in agent_records:
        transition_id = str(record.get("transitionId") or "")
        if not transition_id or transition_id in seen_transition_ids:
            continue
        seen_transition_ids.add(transition_id)

        agent_name = record.get("agentName")
        execution_id = record.get("executionId")

        message = AgentConversationMessage(
            transition_id=transition_id,
            agent_name=str(agent_name) if agent_name is not None else None,
            execution_id=str(execution_id) if execution_id is not None else None,
            timestamp=record.get("timestamp") or 0,
            duration=record.get("duration") or 0,
            edge_type="agent",
            input=record.get("inputContent"),
            output=record.get("outputContent"),
        )
        messages.append(message)
        if message.execution_id:
            messages_by_agent_exec_id[message.execution_id] = message

    def _add_sub_calls(
        records: list[dict[str, Any]], call_type: str, name_field: str
    ) -> None:
        for record in records:
            transition_id = str(record.get("transitionId") or "")
            if not transition_id or transition_id in seen_transition_ids:
                continue
            seen_transition_ids.add(transition_id)

            execution_id = record.get("executionId")
            sub_call = AgentSubCallMessage(
                transition_id=transition_id,
                execution_id=(str(execution_id) if execution_id is not None else None),
                call_type=call_type,
                name=record.get(name_field),
                timestamp=record.get("timestamp") or 0,
                duration=record.get("duration") or 0,
                input=record.get("inputContent"),
                output=record.get("outputContent"),
            )

            parent_agent_exec_id = record.get("parentAgentExecId")
            parent_message = (
                messages_by_agent_exec_id.get(str(parent_agent_exec_id))
                if parent_agent_exec_id
                else None
            )
            if parent_message is not None:
                parent_message.calls.append(sub_call)
            else:
                # No AgentCall claims this call (e.g. a top-level/MAS-level
                # LLM call) -- surface it as its own top-level entry rather
                # than silently dropping it.
                agent_name = record.get("agentName")
                messages.append(
                    AgentConversationMessage(
                        transition_id=transition_id,
                        agent_name=(
                            str(agent_name) if agent_name is not None else None
                        ),
                        execution_id=sub_call.execution_id,
                        timestamp=sub_call.timestamp,
                        duration=sub_call.duration,
                        edge_type=call_type,
                        input=sub_call.input,
                        output=sub_call.output,
                    )
                )

    _add_sub_calls(llm_records, "llm", "modelName")
    _add_sub_calls(tool_records, "tool", "toolName")

    for message in messages:
        message.calls.sort(key=lambda sub_call: sub_call.timestamp)
    messages.sort(key=lambda message: message.timestamp)

    return AgentConversationResponse(
        session_id=session_id,
        messages=messages,
        metadata={
            "graph_type": "agent_conversation",
            "message_count": len(messages),
            "source": "neo4j",
        },
    )


def _get_session_conversation(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
) -> AgentConversationResponse:
    return fetch_agent_conversation(db, session_id=session_id)


def _get_session_latent_space(
    db: Connector,
    dialect: Dialect,
    *,
    session_id: str,
    n_neighbors: int = 15,
    min_dist: float = 0.1,
    random_state: int = 42,
) -> LatentSpaceResponse:
    """Fetch state embeddings and project them to 2D using UMAP."""
    import numpy as np
    from fastapi import HTTPException
    from umap import UMAP

    query, params = ui_queries.latent_space_query(session_id=session_id)
    try:
        records = db.execute(query, params)
    except Exception as exc:
        logger.error(f"[_get_session_latent_space] query failed: {exc}")
        records = []

    state_embeddings: dict[str, list] = {}
    state_data: dict[str, dict] = {}
    transitions: list[dict] = []

    for record in records:
        if not isinstance(record, dict):
            continue

        state_id = record.get("stateId")
        if state_id and state_id not in state_data:
            state_data[state_id] = {
                "content": record.get("content"),
                "semantic_type": record.get("semanticType"),
                "path": record.get("path"),
            }
            embedding = record.get("embedding")
            if embedding is not None:
                state_embeddings[state_id] = embedding

        to_state_id = record.get("toStateId")
        if to_state_id and to_state_id not in state_data:
            state_data[to_state_id] = {
                "content": record.get("toContent"),
                "semantic_type": record.get("toSemanticType"),
                "path": record.get("toPath"),
            }
            to_embedding = record.get("toEmbedding")
            if to_embedding is not None:
                state_embeddings[to_state_id] = to_embedding

        if state_id and to_state_id:
            transitions.append(
                {
                    "from": state_id,
                    "to": to_state_id,
                    "transition_id": record.get("transitionId"),
                    "duration": record.get("duration"),
                    "edge_type": record.get("edgeType"),
                    "entity_name": record.get("entityName"),
                    "entity_type": record.get("entityType"),
                }
            )

    if len(state_embeddings) < 2:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Not enough state embeddings found for session {session_id}. "
                f"Found {len(state_embeddings)}, need at least 2."
            ),
        )

    state_ids = list(state_embeddings.keys())
    embeddings_array = np.array([state_embeddings[sid] for sid in state_ids])

    adjusted_n_neighbors = min(n_neighbors, len(state_ids) - 1)
    if adjusted_n_neighbors < 2:
        adjusted_n_neighbors = 2

    umap_reducer = UMAP(
        n_components=2,
        n_neighbors=adjusted_n_neighbors,
        min_dist=min_dist,
        random_state=random_state,
        metric="cosine",
        n_jobs=1,
    )
    embeddings_2d = umap_reducer.fit_transform(embeddings_array)

    scale = 100.0
    x_min, x_max = embeddings_2d[:, 0].min(), embeddings_2d[:, 0].max()
    y_min, y_max = embeddings_2d[:, 1].min(), embeddings_2d[:, 1].max()
    if x_max - x_min > 0:
        embeddings_2d[:, 0] = (embeddings_2d[:, 0] - x_min) / (
            x_max - x_min
        ) * 2 * scale - scale
    if y_max - y_min > 0:
        embeddings_2d[:, 1] = (embeddings_2d[:, 1] - y_min) / (
            y_max - y_min
        ) * 2 * scale - scale

    position_map = {
        sid: (embeddings_2d[i, 0], embeddings_2d[i, 1])
        for i, sid in enumerate(state_ids)
    }

    nodes: list[LatentSpaceNode] = []
    for sid in state_ids:
        x, y = position_map[sid]
        data = state_data.get(sid, {})
        content = data.get("content", "")
        label = (
            str(content)[:40] + "..."
            if content and len(str(content)) > 40
            else str(content)
            if content
            else sid[:20]
        )
        nodes.append(
            LatentSpaceNode(
                id=sid,
                label=label,
                x=float(x),
                y=float(y),
                type="state",
                data={
                    "state_id": sid,
                    "content": content,
                    "semantic_type": data.get("semantic_type", "intermediate"),
                    "path": data.get("path"),
                },
                metadata={},
            )
        )

    states_without_embeddings = set(state_data.keys()) - set(state_ids)
    for sid in states_without_embeddings:
        data = state_data.get(sid, {})
        content = data.get("content", "")
        label = (
            str(content)[:40] + "..."
            if content and len(str(content)) > 40
            else str(content)
            if content
            else sid[:20]
        )
        nodes.append(
            LatentSpaceNode(
                id=sid,
                label=label,
                x=0.0,
                y=0.0,
                type="state",
                data={
                    "state_id": sid,
                    "content": content,
                    "semantic_type": data.get("semantic_type", "intermediate"),
                    "path": data.get("path"),
                    "has_embedding": False,
                },
                metadata={
                    "color": "#CCCCCC",
                    "shape": "dot",
                    "size": 10,
                    "opacity": 0.5,
                },
            )
        )

    edges: list[LatentSpaceEdge] = []
    added_edge_ids: set[str] = set()
    for trans in transitions:
        edge_id = str(trans["transition_id"] or f"{trans['from']}->{trans['to']}")
        if edge_id in added_edge_ids:
            continue
        added_edge_ids.add(edge_id)
        entity_name = trans["entity_name"] or "unknown"
        edges.append(
            LatentSpaceEdge(
                id=edge_id,
                source=trans["from"],
                target=trans["to"],
                label=entity_name,
                type="transition",
                data={
                    "transition_id": edge_id,
                    "duration": trans["duration"],
                    "edge_type": trans["edge_type"],
                    "entity_name": entity_name,
                    "entity_type": trans["entity_type"],
                },
                metadata={"color": "#888888"},
            )
        )

    return LatentSpaceResponse(
        nodes=nodes,
        edges=edges,
        session_id=session_id,
        metadata={
            "graph_type": "latent_space",
            "projection_method": "UMAP",
            "node_count": len(nodes),
            "edge_count": len(edges),
            "states_with_embeddings": len(state_ids),
            "states_without_embeddings": len(states_without_embeddings),
            "umap_params": {
                "n_neighbors": adjusted_n_neighbors,
                "min_dist": min_dist,
                "metric": "cosine",
            },
            "source": "neo4j",
        },
    )
