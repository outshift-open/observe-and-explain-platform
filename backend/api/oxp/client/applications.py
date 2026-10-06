#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Application-related private implementations for :class:`UIClient`."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from numbers import Real
from typing import Any, Callable, Optional

from oxp.client.constants import (
    ANSWER_RELEVANCY,
    APP_GROUNDEDNESS,
    COST_PER_TOKEN,
    DASH_SEPARATOR,
    INPUT_TOKENS_KEY,
    OUTPUT_TOKENS_KEY,
    PERIODS_COUNT,
    RESPONSE_COMPLETENESS,
    SPACE_SEPARATOR,
    TASK_STATUS_DONE,
    TOOL_UTILIZATION_ACCURACY,
    WORKFLOW_EFFICIENCY,
)
from oxp.client.utils import (
    epoch_to_dt_str,
    parse_epoch_range,
    parse_events_attributes,
    parse_span_attributes,
    parse_time_filters,
    parse_tools_from_repr,
    safe_int,
    timestamp_to_epoch,
)
from oxp.connectors.base import Connector
from oxp.connectors.neo4j import (
    SEMANTICGROUP_NODE_CHILDREN_NODES,
    SEMANTICGROUP_NODE_GROUP_NAME,
    SEMANTICGROUP_NODE_GROUP_SUMMARY,
    SEMANTICGROUP_NODE_ID,
    SEMANTICGROUP_NODE_MEDIOID_SESSION_ID,
    SEMANTICGROUP_NODE_N_SESSIONS,
    SEMANTICGROUP_NODE_OVERALL_PERFORMANCE,
    SEMANTICGROUP_NODE_OVERALL_QUALITY,
    SEMANTICGROUP_NODE_OVERALL_RELIABILITY,
    SEMANTICGROUP_NODE_SESSION_IDS,
    SEMANTICGROUP_NODE_SPLIT_DISTANCE,
)
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    AgentToolItem,
    ApplicationAgentTools,
    ApplicationAgentToolsResponse,
    ApplicationItem,
    ApplicationNameItem,
    ApplicationNamesResponse,
    ApplicationsResponse,
    CollectByApplicationResponse,
    CollectSessionItem,
    Filters,
    ImpactAssementAgentItem,
    ImpactAssessmentMetric,
    ImpactAssessmentResponse,
    MonitorAgentItem,
    MonitorApplicationLevelData,
    MonitorByApplicationResponse,
    MonitorTaskItem,
    MostActiveAgent,
    MultipleValuesData,
    SemanticGroupNode,
    SemanticgroupsResponse,
    SingleValueData,
    TimelineData,
)
from oxp.query_builders import ui as ui_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)


# ── Application descriptions (hardcoded, matching Go resolver) ────────────
_APPLICATION_DESCRIPTIONS: dict[str, str] = {
    "noa": (
        "Network of Assistants (NoA), a sample multi-agent multi-framework "
        "application designed to orchestrate specialized AI assistants to "
        "answer general queries. Think of it as an intelligent network of "
        "AI minds working collaboratively to get the job done!"
    ),
    "poirot": (
        "Poirot is a linear multi\u2011agent question\u2011answering example "
        "that can be invoked via an HTTP endpoint or run in batch on the GAIA "
        "dataset, saving per\u2011question results. It\u2019s instrumented with "
        "OpenTelemetry/Observe for trace logging throughout the agent pipeline."
    ),
    "miss-marple": (
        "A simple linear multi-agent system composed of five agents, designed "
        "to answer general questions by searching the web and reasoning on "
        "data retrieved from the internet."
    ),
}


# ── get_application_names ────────────────────────────────────────────────────


def _get_application_names(
    db: Connector,
    dialect: Dialect,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ApplicationNamesResponse:
    filters = Filters(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    start_dt, end_dt = parse_time_filters(filters)

    stmt = ui_queries.applications_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
        limit=filters.limit,
        offset=filters.offset,
    )

    try:
        rows = db.execute(stmt)
    except Exception as exc:
        raise DatabaseError(f"Failed to get application names: {exc}") from exc
    return ApplicationNamesResponse(
        applications=[
            ApplicationNameItem(
                application_id=str(r[0]),
                start_time=str(r[1]),
            )
            for r in rows
        ]
    )


# ── get_applications ──────────────────────────────────────────────────


def _get_applications_from_clickhouse_multiquery(
    db: Connector,
    dialect: Dialect,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ApplicationsResponse:
    """Return a list of applications with agents, LLMs, cost, and performance.

    Fetches all ``(application_id, session_id)`` pairs, groups by application,
    then enriches each one with agents, LLMs, token cost, and overall performance.
    """
    filters = Filters(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    start_dt, end_dt = parse_time_filters(filters)

    # 1. Fetch (application_id, session_id, max_timestamp) rows ────────
    app_sessions_stmt = ui_queries.applications_with_sessions_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
    )
    try:
        app_session_rows = db.execute(app_sessions_stmt)
    except Exception as exc:
        raise DatabaseError(f"Failed to get applications: {exc}") from exc

    # 2. Build application map and track earliest timestamp ────────────
    application_map: dict[str, list[str]] = {}  # app_id -> [session_ids]
    output_app_map: dict[str, dict] = {}  # app_id -> working dict

    for row in app_session_rows:
        app_id = str(row[0])
        session_id = str(row[1])
        ts = str(row[2])

        if not session_id:
            continue

        if app_id not in output_app_map:
            description = _APPLICATION_DESCRIPTIONS.get(app_id.lower(), "")
            output_app_map[app_id] = {
                "applicationName": app_id,
                "version": 1,
                "description": description,
                "cost": 0.0,
                "costDollars": 0.0,
                "timestamp": ts,
                "llms": [],
                "agents": [],
                "overallPerformance": SingleValueData(value=0.0, unit="PERCENTAGE"),
            }

        # Keep the earliest timestamp
        if ts < output_app_map[app_id]["timestamp"]:
            output_app_map[app_id]["timestamp"] = ts

        application_map.setdefault(app_id, []).append(session_id)

    # 3. For each application, compute metrics ─────────────────────────
    items: list[ApplicationItem] = []

    for app_id, app_data in output_app_map.items():
        session_ids = application_map.get(app_id, [])

        # 3a. Cost (token sum) ─────────────────────────────────────────
        if session_ids:
            cost_stmt = ui_queries.token_sum_by_sessions_clickhouse_query(
                dialect,
                session_ids=session_ids,
            )
            try:
                cost_rows = db.execute(cost_stmt)
            except Exception as exc:
                logger.error("malformed or unexpected data: %s", exc)
                cost_rows = []

            total_tokens = 0
            if dialect is Dialect.SQLITE:
                for cr in cost_rows:
                    attrs = parse_span_attributes(str(cr[0]) if cr[0] else "")
                    total_tokens += safe_int(attrs.get(INPUT_TOKENS_KEY, ""))
                    total_tokens += safe_int(attrs.get(OUTPUT_TOKENS_KEY, ""))
            else:
                if cost_rows and cost_rows[0][0]:
                    total_tokens = int(float(cost_rows[0][0]))

            app_data["cost"] = float(total_tokens)
            app_data["costDollars"] = float(total_tokens) * COST_PER_TOKEN

        # 3b. Agents ───────────────────────────────────────────────────
        if session_ids:
            agents_stmt = ui_queries.agents_by_application_and_sessions_query(
                dialect,
                application_id=app_id,
                session_ids=session_ids,
            )
            try:
                agent_rows = db.execute(agents_stmt)
            except Exception as exc:
                logger.error("malformed or unexpected data: %s", exc)
                agent_rows = []
            app_data["agents"] = [str(ar[0]) for ar in agent_rows if ar[0]]

        # 3c. LLMs ────────────────────────────────────────────────────
        if session_ids:
            llms_stmt = ui_queries.llms_by_application_and_sessions_query(
                dialect,
                application_id=app_id,
                session_ids=session_ids,
            )
            try:
                llm_rows = db.execute(llms_stmt)
            except Exception as exc:
                logger.error("malformed or unexpected data: %s", exc)
                llm_rows = []

            if dialect is Dialect.SQLITE:
                llm_set: set[str] = set()
                for lr in llm_rows:
                    attrs = parse_span_attributes(str(lr[0]) if lr[0] else "")
                    model = attrs.get("gen_ai.request.model", "")
                    if model:
                        llm_set.add(model)
                app_data["llms"] = sorted(llm_set)
            else:
                app_data["llms"] = [str(lr[0]) for lr in llm_rows if lr[0]]

        # 3d. Overall Performance ──────────────────────────────────────
        if session_ids:
            metric_configs = [
                (WORKFLOW_EFFICIENCY, True),
                (APP_GROUNDEDNESS, True),
                (ANSWER_RELEVANCY, False),
                (RESPONSE_COMPLETENESS, True),
                (TOOL_UTILIZATION_ACCURACY, False),
            ]
            metric_values: list[float] = []
            for metric_name, with_category in metric_configs:
                m_stmt = ui_queries.derived_metric_mce_avg_by_sessions_query(
                    dialect,
                    metric_name=metric_name,
                    session_ids=session_ids,
                    with_category=with_category,
                )
                try:
                    m_rows = db.execute(m_stmt)
                except Exception as exc:
                    logger.error("derived metric {metric_name}: %s", exc)
                    m_rows = []
                val = float(m_rows[0][0]) if m_rows and m_rows[0][0] else 0.0
                metric_values.append(val)

            if metric_values:
                overall_avg = sum(metric_values) / len(metric_values)
                app_data["overallPerformance"] = SingleValueData(
                    value=round(overall_avg * 100, 2),
                    unit="PERCENTAGE",
                )

        items.append(ApplicationItem(**app_data))

    return ApplicationsResponse(applications=items)


def _get_applications_multiquery(
    db: Connector,
    dialect: Dialect,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ApplicationsResponse:
    """Return applications data sourced entirely from Neo4j.

    Mirrors :func:`_get_applications_from_clickhouse_multiquery` output while retrieving
    sessions, agents, LLMs, token usage and performance metrics from KG nodes.
    """
    del dialect  # Neo4j query path is explicit in this function.

    def _to_float(value: Any) -> float | None:
        """Best-effort conversion of metric payloads to a float value."""
        if value is None:
            return None
        if isinstance(value, Real) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
            try:
                parsed = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return None
            if isinstance(parsed, Real) and not isinstance(parsed, bool):
                return float(parsed)
            if isinstance(parsed, dict):
                raw_val = parsed.get("value")
                if isinstance(raw_val, Real) and not isinstance(raw_val, bool):
                    return float(raw_val)
        if isinstance(value, dict):
            raw_val = value.get("value")
            if isinstance(raw_val, Real) and not isinstance(raw_val, bool):
                return float(raw_val)
        return None

    # Filter bounds are epoch seconds in this codebase.
    start_epoch: float | None = None
    end_epoch: float | None = None
    try:
        if start_time not in (None, ""):
            start_epoch = float(start_time)
    except (TypeError, ValueError):
        start_epoch = None
    try:
        if end_time not in (None, ""):
            end_epoch = float(end_time)
    except (TypeError, ValueError):
        end_epoch = None

    # 1) Fetch app-level aggregates and session IDs from Neo4j.
    app_rows_stmt, app_rows_params = ui_queries.neo4j_applications_with_sessions_query(
        Dialect.NEO4J,
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        offset=offset,
        limit=limit,
    )
    try:
        app_rows = db.execute(app_rows_stmt, app_rows_params)
    except Exception as exc:
        raise DatabaseError(f"Failed to get applications from Neo4j: {exc}") from exc

    items: list[ApplicationItem] = []
    metric_names = [
        WORKFLOW_EFFICIENCY,
        APP_GROUNDEDNESS,
        ANSWER_RELEVANCY,
        RESPONSE_COMPLETENESS,
        TOOL_UTILIZATION_ACCURACY,
    ]

    # 2) Enrich each application using its session set.
    for row in app_rows:
        app_id = str(row.get("application_id") or "")
        if not app_id:
            continue

        session_ids = [str(sid) for sid in (row.get("session_ids") or []) if sid]
        if not session_ids:
            continue

        min_start = row.get("min_start")
        timestamp = ""
        if isinstance(min_start, Real) and not isinstance(min_start, bool):
            timestamp = str(float(min_start))

        # Tokens from LLMCall nodes for the selected sessions.
        tokens_stmt, tokens_params = ui_queries.token_sum_by_sessions_query(
            session_ids=session_ids,
        )
        try:
            token_rows = db.execute(tokens_stmt, tokens_params)
        except Exception as exc:
            logger.error("neo4j token query failed for %s: %s", app_id, exc)
            token_rows = []
        total_tokens = 0
        if token_rows:
            raw_tokens = token_rows[0].get("total_tokens")
            if raw_tokens is not None:
                total_tokens = int(float(raw_tokens))

        # Distinct agents for sessions.
        agents_stmt, agents_params = (
            ui_queries.agents_by_application_and_sessions_query(
                Dialect.NEO4J,
                application_id=app_id,
                session_ids=session_ids,
            )
        )
        try:
            agent_rows = db.execute(agents_stmt, agents_params)
        except Exception as exc:
            logger.error("neo4j agents query failed for %s: %s", app_id, exc)
            agent_rows = []
        agents = []
        if agent_rows:
            agents = sorted(str(a) for a in (agent_rows[0].get("agents") or []) if a)

        # Distinct LLM model names for sessions.
        llms_stmt, llms_params = ui_queries.llms_by_application_and_sessions_query(
            Dialect.NEO4J,
            application_id=app_id,
            session_ids=session_ids,
        )
        try:
            llm_rows = db.execute(llms_stmt, llms_params)
        except Exception as exc:
            logger.error("neo4j llm query failed for %s: %s", app_id, exc)
            llm_rows = []
        llms = []
        if llm_rows:
            llms = sorted(
                str(llm_name)
                for llm_name in (llm_rows[0].get("llms") or [])
                if llm_name
            )

        # Session-attached metrics.
        metrics_stmt, metrics_params = ui_queries.session_metrics_by_name_query(
            Dialect.NEO4J,
            session_ids=session_ids,
            metric_names=metric_names,
        )
        try:
            metric_rows = db.execute(metrics_stmt, metrics_params)
        except Exception as exc:
            logger.error("neo4j metric query failed for %s: %s", app_id, exc)
            metric_rows = []

        # Match _get_applications_from_clickhouse_multiquery strategy: per-session avg per
        # metric, then average each metric across sessions, then average metrics.
        per_metric_per_session: dict[str, dict[str, float]] = {}
        for mr in metric_rows:
            sid = str(mr.get("sid") or "")
            metric_name = str(mr.get("metric_name") or "")
            if not sid or not metric_name:
                continue
            values = [_to_float(v) for v in (mr.get("metric_results") or [])]
            valid_values = [v for v in values if v is not None]
            if not valid_values:
                continue
            per_session_avg = sum(valid_values) / len(valid_values)
            per_metric_per_session.setdefault(metric_name, {})[sid] = per_session_avg

        metric_avgs: list[float] = []
        for metric_name in metric_names:
            sid_map = per_metric_per_session.get(metric_name, {})
            if sid_map:
                metric_avgs.append(sum(sid_map.values()) / len(sid_map))
            else:
                metric_avgs.append(0.0)

        overall_perf = 0.0
        if metric_avgs:
            overall_perf = (sum(metric_avgs) / len(metric_avgs)) * 100.0

        description = _APPLICATION_DESCRIPTIONS.get(app_id.lower(), "")
        items.append(
            ApplicationItem(
                applicationName=app_id,
                version=1,
                description=description,
                cost=float(total_tokens),
                costDollars=float(total_tokens) * COST_PER_TOKEN,
                timestamp=timestamp,
                llms=llms,
                agents=agents,
                overallPerformance=SingleValueData(
                    value=round(overall_perf, 2),
                    unit="PERCENTAGE",
                ),
            )
        )

    return ApplicationsResponse(applications=items)


def _get_applications(
    db: Connector,
    dialect: Dialect,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ApplicationsResponse:
    """Return Neo4j applications using a single consolidated Cypher query.

    This mirrors :func:`_get_applications_multiquery` response shape while reducing per-application query fan-out.
    """
    del dialect  # Neo4j query path is explicit in this function.

    def _to_float(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, Real) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
            try:
                parsed = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                return None
            if isinstance(parsed, Real) and not isinstance(parsed, bool):
                return float(parsed)
            if isinstance(parsed, dict):
                raw_val = parsed.get("value")
                if isinstance(raw_val, Real) and not isinstance(raw_val, bool):
                    return float(raw_val)
        if isinstance(value, dict):
            raw_val = value.get("value")
            if isinstance(raw_val, Real) and not isinstance(raw_val, bool):
                return float(raw_val)
        return None

    start_epoch: float | None = None
    end_epoch: float | None = None
    try:
        if start_time not in (None, ""):
            start_epoch = float(start_time)
    except (TypeError, ValueError):
        start_epoch = None
    try:
        if end_time not in (None, ""):
            end_epoch = float(end_time)
    except (TypeError, ValueError):
        end_epoch = None

    metric_names = [
        WORKFLOW_EFFICIENCY,
        APP_GROUNDEDNESS,
        ANSWER_RELEVANCY,
        RESPONSE_COMPLETENESS,
        TOOL_UTILIZATION_ACCURACY,
    ]

    stmt, params = ui_queries.neo4j_applications_with_metrics_optimized_query(
        Dialect.NEO4J,
        start_epoch=start_epoch,
        end_epoch=end_epoch,
        offset=offset,
        limit=limit,
        metric_names=metric_names,
    )
    try:
        rows = db.execute(stmt, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get optimized applications from Neo4j: {exc}"
        ) from exc

    items: list[ApplicationItem] = []

    for row in rows:
        app_id = str(row.get("application_id") or "")
        if not app_id:
            continue

        session_ids = [str(sid) for sid in (row.get("session_ids") or []) if sid]
        if not session_ids:
            continue

        min_start = row.get("min_start")
        timestamp = ""
        if isinstance(min_start, Real) and not isinstance(min_start, bool):
            timestamp = str(float(min_start))

        total_tokens = int(float(row.get("total_tokens") or 0.0))
        agents = sorted(str(a) for a in (row.get("agents") or []) if a)
        llms = sorted(str(llm_name) for llm_name in (row.get("llms") or []) if llm_name)

        per_metric_per_session: dict[str, dict[str, list[float]]] = {}
        for mr in row.get("metric_rows") or []:
            sid = str((mr or {}).get("sid") or "")
            metric_name = str((mr or {}).get("metric_name") or "")
            if not sid or not metric_name:
                continue
            metric_value = _to_float((mr or {}).get("metric_result"))
            if metric_value is None:
                continue
            per_metric_per_session.setdefault(metric_name, {}).setdefault(
                sid, []
            ).append(metric_value)

        metric_avgs: list[float] = []
        for metric_name in metric_names:
            sid_map = per_metric_per_session.get(metric_name, {})
            if sid_map:
                per_session_avgs = [
                    (sum(values) / len(values)) for values in sid_map.values() if values
                ]
                metric_avgs.append(
                    (sum(per_session_avgs) / len(per_session_avgs))
                    if per_session_avgs
                    else 0.0
                )
            else:
                metric_avgs.append(0.0)

        overall_perf = 0.0
        if metric_avgs:
            overall_perf = (sum(metric_avgs) / len(metric_avgs)) * 100.0

        description = _APPLICATION_DESCRIPTIONS.get(app_id.lower(), "")
        items.append(
            ApplicationItem(
                applicationName=app_id,
                version=1,
                description=description,
                cost=float(total_tokens),
                costDollars=float(total_tokens) * COST_PER_TOKEN,
                timestamp=timestamp,
                llms=llms,
                agents=agents,
                overallPerformance=SingleValueData(
                    value=round(overall_perf, 2),
                    unit="PERCENTAGE",
                ),
            )
        )

    return ApplicationsResponse(applications=items)


def _get_applications_from_clickhouse(
    db: Connector,
    dialect: Dialect,
    *,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> ApplicationsResponse:
    """Return a list of applications with agents, LLMs, cost, and performance.

    Uses a single merged query to fetch sessions and token costs in one pass,
    avoiding the N+1 pattern of the non-optimized version.
    """
    filters = Filters(
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )
    start_dt, end_dt = parse_time_filters(filters)

    # 1. Single query: (application_id, session_id, max_timestamp, token_data) ─
    stmt = ui_queries.applications_with_sessions_and_tokens_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
    )
    try:
        rows = db.execute(stmt)
    except Exception as exc:
        raise DatabaseError(f"Failed to get applications: {exc}") from exc

    # 2. Build maps and accumulate tokens in one pass ──────────────────
    # ClickHouse query groups by (application_id, session_id), so each row
    # is unique and total_tokens is already aggregated per session.
    application_map: dict[str, list[str]] = {}  # app_id -> [session_ids]
    output_app_map: dict[str, dict] = {}  # app_id -> working dict
    token_accum: dict[str, int] = {}  # app_id -> total_tokens

    for row in rows:
        app_id = str(row[0])
        session_id = str(row[1])
        ts = str(row[2])
        token_col = row[3]
        agents_col = row[4] if row[4] else []
        llms_col = row[5] if row[5] else []

        if not session_id:
            continue

        if app_id not in output_app_map:
            description = _APPLICATION_DESCRIPTIONS.get(app_id.lower(), "")
            output_app_map[app_id] = {
                "applicationName": app_id,
                "version": 1,
                "description": description,
                "cost": 0.0,
                "costDollars": 0.0,
                "timestamp": ts,
                "llms": [],
                "agents": [],
                "overallPerformance": SingleValueData(value=0.0, unit="PERCENTAGE"),
            }
            token_accum[app_id] = 0

        if ts < output_app_map[app_id]["timestamp"]:
            output_app_map[app_id]["timestamp"] = ts

        # agents and llms are app-level aggregates — same value on every row
        # for the same application; overwriting is safe.
        output_app_map[app_id]["agents"] = [str(a) for a in agents_col if a]
        output_app_map[app_id]["llms"] = sorted(str(llm) for llm in llms_col if llm)

        application_map.setdefault(app_id, []).append(session_id)

        if token_col:
            token_accum[app_id] += int(float(token_col))

    # Assign accumulated token costs
    for app_id, total_tokens in token_accum.items():
        output_app_map[app_id]["cost"] = float(total_tokens)
        output_app_map[app_id]["costDollars"] = float(total_tokens) * COST_PER_TOKEN

    # 3. Single query for all MCE metrics across all sessions ─────────
    all_session_ids = [sid for sids in application_map.values() for sid in sids]
    session_metrics: dict[str, tuple[Optional[float], ...]] = {}

    if all_session_ids:
        metrics_stmt = ui_queries.all_mce_metrics_by_sessions_query(
            dialect,
            session_ids=all_session_ids,
        )
        try:
            metrics_rows = db.execute(metrics_stmt)
        except Exception as exc:
            logger.error("mce metrics batch query: %s", exc)
            metrics_rows = []

        all_session_ids_set = set(all_session_ids)
        for mr in metrics_rows:
            raw_sid = str(mr[0])
            # derived_metrics.SessionId may carry an application-name prefix
            # (e.g. "app-name_uuid"); normalise to the bare UUID we know.
            if raw_sid in all_session_ids_set:
                bare_sid = raw_sid
            elif len(raw_sid) >= 36 and raw_sid[-36:] in all_session_ids_set:
                bare_sid = raw_sid[-36:]
            else:
                continue
            new_vals = tuple(
                float(v) if v is not None else None
                for v in (mr[1], mr[2], mr[3], mr[4], mr[5])
            )
            if bare_sid in session_metrics:
                # The same bare UUID can appear twice (once bare, once prefixed).
                # Merge by keeping the non-None value for each metric column.
                prev = session_metrics[bare_sid]
                session_metrics[bare_sid] = tuple(
                    nv if pv is None else pv for pv, nv in zip(prev, new_vals)
                )
            else:
                session_metrics[bare_sid] = new_vals

    # 4. Compute per-application overall performance from session metrics ─
    items: list[ApplicationItem] = []

    for app_id, app_data in output_app_map.items():
        session_ids = application_map.get(app_id, [])

        metric_cols: list[list[float]] = [[], [], [], [], []]
        for sid in session_ids:
            if sid in session_metrics:
                for i, v in enumerate(session_metrics[sid]):
                    if v is not None:  # None means no data for this metric
                        metric_cols[i].append(v)

        metric_avgs = [sum(col) / len(col) if col else 0.0 for col in metric_cols]
        if metric_avgs:
            overall_avg = sum(metric_avgs) / len(metric_avgs)
            app_data["overallPerformance"] = SingleValueData(
                value=round(overall_avg * 100, 2),
                unit="PERCENTAGE",
            )

        items.append(ApplicationItem(**app_data))

    return ApplicationsResponse(applications=items)


def _get_application_details(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> MonitorApplicationLevelData:
    """Return application-level monitoring data for a given application.

    When *given_session_ids* is provided, start/end time are overridden
    based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)
    period_size = (end_epoch - start_epoch) / PERIODS_COUNT

    # If session IDs are provided, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                time_range = max_epoch - min_epoch
                if time_range < 10:
                    max_epoch = min_epoch + 10
                period_size = (max_epoch - min_epoch) / (PERIODS_COUNT - 2)
                start_epoch = max(min_epoch - period_size, 0)
                end_epoch = max_epoch + period_size

    # Build the timeline (totalTokens / totalCost per time bucket)
    total_tokens_timeline: list[TimelineData] = []
    total_cost_timeline: list[TimelineData] = []

    current = start_epoch
    while current < end_epoch:
        bucket_start_dt = epoch_to_dt_str(current)
        bucket_end_dt = epoch_to_dt_str(current + period_size)

        # Session IDs that fall into this time bucket
        bucket_stmt = ui_queries.session_ids_graph_query(
            dialect,
            start_time=bucket_start_dt,
            end_time=bucket_end_dt,
            application_id=application_id,
            given_session_ids=given_session_ids,
        )
        try:
            bucket_rows = db.execute(bucket_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            bucket_rows = []
        bucket_session_ids = [str(r[0]) for r in bucket_rows]

        timestamp_iso = datetime.fromtimestamp(
            current,
            tz=timezone.utc,
        ).isoformat()

        total_tokens_timeline.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=0, unit="SCALAR"),
            )
        )
        total_cost_timeline.append(
            TimelineData(
                timestamp=timestamp_iso,
                sessionIDs=bucket_session_ids,
                value=SingleValueData(value=0, unit="DOLLAR"),
            )
        )

        current += period_size

    # All session IDs across the full time range
    start_dt = epoch_to_dt_str(start_epoch)
    end_dt = epoch_to_dt_str(end_epoch)

    all_stmt = ui_queries.session_ids_graph_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
        application_id=application_id,
        given_session_ids=given_session_ids,
    )
    try:
        all_rows = db.execute(all_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        all_rows = []
    [str(r[0]) for r in all_rows]

    # All session IDs for the application (no graph-span filter) — used
    # for MCE/derived-metric queries whose rows are not tied to graph spans.
    app_sessions_stmt = ui_queries.applications_with_sessions_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
    )
    try:
        app_sessions_rows = db.execute(app_sessions_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        app_sessions_rows = []
    all_app_session_ids = [
        str(r[1])
        for r in app_sessions_rows
        if r[0] and str(r[0]).lower() == application_id.lower()
    ]
    if given_session_ids:
        given_set = set(given_session_ids)
        all_app_session_ids = [s for s in all_app_session_ids if s in given_set]

    # Initialise the response with defaults
    result = MonitorApplicationLevelData(
        traces=SingleValueData(value=0, unit="SCALAR"),
        totalTokens=total_tokens_timeline,
        totalCost=total_cost_timeline,
        sessionDuration=SingleValueData(value=0, unit="MILLISECONDS"),
        workflowEfficiency=SingleValueData(value=0, unit="PERCENTAGE"),
        answerGroundedness=SingleValueData(value=0, unit="PERCENTAGE"),
        answerRelevancy=SingleValueData(value=0, unit="PERCENTAGE"),
        overallTaskCompletion=SingleValueData(value=0, unit="PERCENTAGE"),
        toolUtilisationAccuracyScore=SingleValueData(value=0, unit="PERCENTAGE"),
        overallPerformanceScore=SingleValueData(value=0, unit="PERCENTAGE"),
        toxicity=SingleValueData(value=0, unit="PERCENTAGE"),
        errorCount=SingleValueData(value=0, unit="SCALAR"),
        mostFrequentErrors=MultipleValuesData(count=0, items=[]),
        sessions=SingleValueData(value=float(len(all_app_session_ids)), unit="SCALAR"),
        llmCalls=SingleValueData(value=0, unit="SCALAR"),
        toolCalls=SingleValueData(value=0, unit="SCALAR"),
        totalActionCount=SingleValueData(value=0, unit="SCALAR"),
        totalConversationCount=SingleValueData(value=0, unit="SCALAR"),
        graphDeterminism=SingleValueData(value=0, unit="PERCENTAGE"),
        graphDynamism=SingleValueData(value=0, unit="PERCENTAGE"),
        mostActiveAgent=MostActiveAgent(agentName=""),
    )

    if not all_app_session_ids:
        return result

    # ── Traces count ─────────────────────────────────────────────────
    traces_stmt = ui_queries.traces_count_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
        application_id=application_id,
    )
    try:
        traces_rows = db.execute(traces_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        traces_rows = []
    if traces_rows:
        result.traces.value = float(traces_rows[0][0])

    # ── Conversation count (distinct agent_id × session pairs) ───────
    conv_stmt = ui_queries.conversation_count_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
        application_id=application_id,
    )
    try:
        conv_rows = db.execute(conv_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        conv_rows = []
    if conv_rows:
        result.totalConversationCount.value = float(conv_rows[0][0])

    # ── Most active agent ────────────────────────────────────────────

    best_agent = ""
    best_count = 0
    one_query_stmt = ui_queries.top_agent_span_count_for_sessions_query(
        dialect,
        session_ids=all_app_session_ids,
    )
    try:
        one_query_rows = db.execute(one_query_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        one_query_rows = []
    if one_query_rows:
        best_agent = str(one_query_rows[0][0]) if one_query_rows[0][0] else ""
        best_count = int(one_query_rows[0][1]) if one_query_rows[0][1] else 0

    if best_agent:
        # Title-case and replace dashes with spaces
        display_name = best_agent.replace("-", " ").title()
        result.mostActiveAgent.agentName = display_name
        result.mostActiveAgent.activity.value = float(best_count)

    # ── PassiveEvalApp aggregate (duration, llm/tool calls, graph metrics) ──
    passive_stmt = ui_queries.passive_eval_app_avg_by_sessions_query(
        dialect,
        session_ids=all_app_session_ids,
    )
    try:
        passive_rows = db.execute(passive_stmt)
    except Exception as exc:
        logger.error("PassiveEvalApp query: %s", exc)
        passive_rows = []

    if passive_rows and any(v is not None for v in passive_rows[0]):
        pr = passive_rows[0]

        # columns: tool_calls, tool_fails, llm_calls, llm_fails, llm_cost,
        #          duration, graph_determinism, graph_dynamism
        def _fval(v) -> float:
            return round(float(v), 6) if v is not None else 0.0

        tool_calls_avg = _fval(pr[0])
        tool_fails_avg = _fval(pr[1])
        llm_calls_avg = _fval(pr[2])
        llm_fails_avg = _fval(pr[3])
        duration_avg_ms = _fval(pr[5])  # already in milliseconds
        graph_det = _fval(pr[6])
        graph_dyn = _fval(pr[7])

        # Use AVG values directly — matches Go GetDerivedMetricSDKAggregatedAvgBySessionIDs
        result.llmCalls.value = round(llm_calls_avg, 2)
        result.toolCalls.value = round(tool_calls_avg, 2)
        result.totalActionCount.value = result.llmCalls.value + result.toolCalls.value
        result.errorCount.value = round(llm_fails_avg + tool_fails_avg, 2)
        result.sessionDuration.value = round(duration_avg_ms, 2)
        result.graphDeterminism.value = round(graph_det * 100, 2)
        result.graphDynamism.value = round(graph_dyn * 100, 2)
    else:
        # Fallback: derive from otel_traces spans ─────────────────────────
        # ── Session duration (avg across sessions) ────────────────────
        sess_dur_stmt = ui_queries.session_avg_duration_for_sessions_query(
            dialect,
            session_ids=all_app_session_ids,
        )
        try:
            sess_dur_rows = db.execute(sess_dur_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            sess_dur_rows = []
        if sess_dur_rows and sess_dur_rows[0][0]:
            result.sessionDuration.value = round(float(sess_dur_rows[0][0]) * 1000, 2)

        # ── LLM calls count ───────────────────────────────────────────
        llm_calls_stmt = ui_queries.llm_calls_count_by_sessions_query(
            dialect,
            session_ids=all_app_session_ids,
        )
        try:
            llm_calls_rows = db.execute(llm_calls_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            llm_calls_rows = []
        if llm_calls_rows and llm_calls_rows[0][0]:
            result.llmCalls.value = float(llm_calls_rows[0][0])

        # ── Tool calls count ──────────────────────────────────────────
        tool_calls_stmt = ui_queries.tool_calls_count_by_sessions_query(
            dialect,
            session_ids=all_app_session_ids,
        )
        try:
            tool_calls_rows = db.execute(tool_calls_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            tool_calls_rows = []
        if tool_calls_rows and tool_calls_rows[0][0]:
            result.toolCalls.value = float(tool_calls_rows[0][0])

        result.totalActionCount.value = result.llmCalls.value + result.toolCalls.value

        # ── Error count ───────────────────────────────────────────────
        error_stmt = ui_queries.error_count_by_sessions_query(
            dialect,
            session_ids=all_app_session_ids,
        )
        try:
            error_rows = db.execute(error_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            error_rows = []
        if error_rows and error_rows[0][0]:
            result.errorCount.value = float(error_rows[0][0])

    # ── Derived MCE metrics ───────────────────────────────────────────
    derived_metric_configs = [
        (WORKFLOW_EFFICIENCY, False, "workflowEfficiency"),
        (APP_GROUNDEDNESS, False, "answerGroundedness"),
        (ANSWER_RELEVANCY, False, "answerRelevancy"),
        (RESPONSE_COMPLETENESS, False, "overallTaskCompletion"),
        (TOOL_UTILIZATION_ACCURACY, False, "toolUtilisationAccuracyScore"),
    ]
    perf_values: list[float] = []
    for metric_name, with_category, field_name in derived_metric_configs:
        m_stmt = ui_queries.derived_metric_mce_avg_by_sessions_query(
            dialect,
            metric_name=metric_name,
            session_ids=all_app_session_ids,
            with_category=with_category,
        )
        try:
            m_rows = db.execute(m_stmt)
        except Exception as exc:
            logger.error("derived metric {metric_name}: %s", exc)
            m_rows = []
        val = float(m_rows[0][0]) if m_rows and m_rows[0][0] else 0.0
        pct = round(val * 100, 2)
        getattr(result, field_name).value = pct
        perf_values.append(val)

    if perf_values:
        overall_avg = sum(perf_values) / len(perf_values)
        result.overallPerformanceScore.value = round(overall_avg * 100, 2)

    # ── Populate totalTokens / totalCost timeline values ──────────────
    for tl_item_tokens, tl_item_cost in zip(result.totalTokens, result.totalCost):
        bucket_session_ids = tl_item_tokens.sessionIDs
        if not bucket_session_ids:
            continue

        metric_stmt = ui_queries.derived_metric_sdk_avg_by_sessions_query(
            dialect, session_ids=bucket_session_ids, metric_name="eval.app.llm_cost"
        )
        try:
            metric_rows = db.execute(metric_stmt)
        except Exception as exc:
            logger.error("derived metric: %s", exc)
            metric_rows = []

        bucket_tokens = 0.0
        if metric_rows and metric_rows[0][0]:
            bucket_tokens = float(metric_rows[0][0])

        tl_item_tokens.value.value = bucket_tokens
        tl_item_cost.value.value = round(bucket_tokens * COST_PER_TOKEN, 6)

    return result


# ── get_application_agent_tools ──────────────────────────────────────────────


def _get_application_agent_tools(
    db: Connector,
    *,
    application_id: str,
) -> ApplicationAgentToolsResponse:
    """Return each agent's tools for an application, from Neo4j structural data."""
    query, params = ui_queries.agent_tools_by_application_query(
        application_id=application_id,
    )
    try:
        rows = db.execute(query, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get agent tools for application '{application_id}': {exc}"
        ) from exc

    agents: list[ApplicationAgentTools] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        agents.append(
            ApplicationAgentTools(
                agent_id=str(row.get("agentId") or ""),
                agent_name=str(row.get("agentName") or ""),
                agent_description=row.get("agentDescription") or None,
                tools=[
                    AgentToolItem(
                        name=str(tool.get("name") or ""),
                        description=tool.get("description") or None,
                    )
                    for tool in (row.get("tools") or [])
                    if tool and tool.get("name")
                ],
            )
        )

    return ApplicationAgentToolsResponse(
        application_id=application_id,
        agents=agents,
    )


# ── get_application_agents ───────────────────────────────────────────────────


def _get_application_agents(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    start_time: str = "",
    end_time: str = "",
    given_session_ids: Optional[list[str]] = None,
) -> MonitorByApplicationResponse:
    """Return per-agent monitoring data for a given application.

    When *given_session_ids* is provided, start/end time are overridden
    based on the actual timestamps of those sessions.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # If session IDs are provided, override the time range
    if given_session_ids:
        ts_stmt = ui_queries.timestamps_for_sessions_query(
            dialect,
            session_ids=given_session_ids,
        )
        try:
            ts_rows = db.execute(ts_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            ts_rows = []
        if ts_rows and ts_rows[0][0] and ts_rows[0][1]:
            min_ts_str = str(ts_rows[0][0])
            max_ts_str = str(ts_rows[0][1])
            min_epoch = timestamp_to_epoch(min_ts_str)
            max_epoch = timestamp_to_epoch(max_ts_str)
            if min_epoch > 0 and max_epoch > 0:
                start_epoch = min_epoch
                end_epoch = max_epoch

    start_dt = epoch_to_dt_str(start_epoch)
    end_dt = epoch_to_dt_str(end_epoch)

    # Get session IDs for the application in the time range
    sessions_stmt = ui_queries.session_ids_graph_query(
        dialect,
        start_time=start_dt,
        end_time=end_dt,
        application_id=application_id,
        given_session_ids=given_session_ids,
    )
    try:
        session_rows = db.execute(sessions_stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get application agents for '{application_id}': {exc}"
        ) from exc
    session_ids_list = [str(r[0]) for r in session_rows if str(r[0])]

    # Initialise response with defaults
    result = MonitorByApplicationResponse(
        totalCost=0.0,
        avgDuration=0.0,
        duration=0.0,
        overrallTaskCompletion=0.0,
        overrallActionAdvancement=0.0,
        agents=[],
    )

    if not session_ids_list:
        return result

    # Get distinct agent names for the sessions
    agents_stmt = ui_queries.distinct_agents_for_sessions_query(
        dialect,
        session_ids=session_ids_list,
    )
    try:
        agent_rows = db.execute(agents_stmt)
    except Exception as exc:
        logger.error("malformed or unexpected data: %s", exc)
        agent_rows = []

    total_cost = 0.0
    total_duration = 0.0
    agent_count = 0

    for row in agent_rows:
        task_name = str(row[0])
        if not task_name:
            continue

        # Build display name: replace dashes with spaces, title-case
        display_name = task_name.replace(
            DASH_SEPARATOR,
            SPACE_SEPARATOR,
        ).title()

        # ── Failures ─────────────────────────────────────────────
        fail_stmt = ui_queries.agent_failure_count_for_sessions_query(
            dialect,
            session_ids=session_ids_list,
            agent_id=task_name,
        )
        try:
            fail_rows = db.execute(fail_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            fail_rows = []
        failures = int(fail_rows[0][0]) if fail_rows else 0

        # ── Recovery rate ────────────────────────────────────────
        recovery_rate = 100.0
        if failures > 0:
            # Without a dedicated recovery metric, assume no recoveries
            # and set rate to 0 when there are failures.
            recovery_rate = 0.0

        # ── Token costs (LLM) ───────────────────────────────────
        token_stmt = ui_queries.agent_token_costs_for_sessions_query(
            dialect,
            session_ids=session_ids_list,
            agent_id=task_name,
        )
        try:
            token_rows = db.execute(token_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            token_rows = []

        llm_total_tokens = 0
        session_set: set[str] = set()
        for trow in token_rows:
            attrs = parse_span_attributes(str(trow[0]) if trow[0] else "")
            llm_total_tokens += safe_int(attrs.get(INPUT_TOKENS_KEY, ""))
            llm_total_tokens += safe_int(attrs.get(OUTPUT_TOKENS_KEY, ""))
            session_set.add(str(trow[1]))

        llm_cost_dollars = llm_total_tokens * COST_PER_TOKEN
        num_sessions_with_data = max(len(session_set), 1)

        # Average across sessions (matches the Go avg-by-sessions logic)
        avg_llm_cost_dollars = llm_cost_dollars / num_sessions_with_data
        avg_llm_tokens = llm_total_tokens / num_sessions_with_data

        agent_cost = avg_llm_cost_dollars
        agent_cost_tokens = avg_llm_tokens

        # Task cost uses LLM tokens * COST_PER_TOKEN (averaged)
        task_cost = avg_llm_cost_dollars

        # ── Utilisation & activity ───────────────────────────────
        active_stmt = ui_queries.agent_active_sessions_query(
            dialect,
            session_ids=session_ids_list,
            agent_id=task_name,
        )
        try:
            active_rows = db.execute(active_stmt)
        except Exception as exc:
            logger.error("malformed or unexpected data: %s", exc)
            active_rows = []
        active_sessions = [str(r[0]) for r in active_rows]
        utilisation = (
            len(active_sessions) / len(session_ids_list) if session_ids_list else 0.0
        )

        # Activity: agent_duration / session_duration
        activity = 0.0
        if active_sessions:
            agent_dur_stmt = ui_queries.agent_avg_duration_for_sessions_query(
                dialect,
                session_ids=active_sessions,
                agent_id=task_name,
            )
            try:
                agent_dur_rows = db.execute(agent_dur_stmt)
            except Exception as exc:
                logger.error("malformed or unexpected data: %s", exc)
                agent_dur_rows = []
            agent_avg_duration = (
                float(agent_dur_rows[0][0])
                if agent_dur_rows and agent_dur_rows[0][0]
                else 0.0
            )

            sess_dur_stmt = ui_queries.session_avg_duration_for_sessions_query(
                dialect,
                session_ids=active_sessions,
            )
            try:
                sess_dur_rows = db.execute(sess_dur_stmt)
            except Exception as exc:
                logger.error("malformed or unexpected data: %s", exc)
                sess_dur_rows = []
            sess_avg_duration = (
                float(sess_dur_rows[0][0])
                if sess_dur_rows and sess_dur_rows[0][0]
                else 0.0
            )

            if sess_avg_duration > 0:
                # agent duration is in nanoseconds, session in seconds
                agent_dur_seconds = agent_avg_duration / 1_000_000_000
                activity = agent_dur_seconds / sess_avg_duration
        else:
            agent_avg_duration = 0.0

        # Round percentages to 2 decimal places (* 100 for percent)
        utilisation_pct = round(utilisation * 100, 2)
        activity_pct = round(activity * 100, 2)

        # ── Duration (nanoseconds → milliseconds for task) ───────
        task_duration = agent_avg_duration / 1_000_000 if agent_avg_duration else 0.0

        # ── Build task ───────────────────────────────────────────
        task_item = MonitorTaskItem(
            id=task_name,
            name=task_name,
            status=TASK_STATUS_DONE,
            duration=task_duration,
            cost=SingleValueData(value=task_cost, unit="DOLLAR"),
        )

        # ── Build agent ──────────────────────────────────────────
        agent_item = MonitorAgentItem(
            id=task_name,
            name=display_name,
            failures=failures,
            recoveryRate=recovery_rate,
            cost=SingleValueData(value=agent_cost, unit="DOLLAR"),
            costTokens=SingleValueData(value=agent_cost_tokens, unit="SCALAR"),
            utilisation=SingleValueData(value=utilisation_pct, unit="PERCENTAGE"),
            activity=SingleValueData(value=activity_pct, unit="PERCENTAGE"),
            tasks=[task_item],
        )

        result.agents.append(agent_item)

        total_cost += agent_cost
        total_duration += task_duration
        agent_count += 1

    result.totalCost = total_cost
    result.duration = total_duration
    result.avgDuration = total_duration / agent_count if agent_count else 0.0

    return result


# ── get_application_sessions ─────────────────────────────────────────────────


def _get_application_sessions(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    start_time: str = "",
    end_time: str = "",
) -> CollectByApplicationResponse:
    """Return collect-by-application data for a given application.

    Aggregates session-level metrics (agents, LLMs, tokens, cost,
    duration) for all sessions belonging to *application* within the
    given time range.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    start_dt = epoch_to_dt_str(start_epoch)
    end_dt = epoch_to_dt_str(end_epoch)

    sessions_stmt = ui_queries.collect_page_sessions_query(
        dialect=Dialect.NEO4J,
        start_time=start_dt,
        end_time=end_dt,
        application_id=application_id,
    )
    try:
        # Query builders may return either a bare query string or a (query, params)
        # tuple for drivers that support parameters (Neo4j). Handle both.
        if isinstance(sessions_stmt, tuple):
            query, params = sessions_stmt
            rows = db.execute(query, params)
        else:
            rows = db.execute(sessions_stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get application sessions for '{application_id}': {exc}"
        ) from exc

    if not rows:
        return CollectByApplicationResponse()

    session_list: list[CollectSessionItem] = []
    total_duration = 0.0

    for row in rows:
        session_item = CollectSessionItem(
            sessionId=str(row["sessionId"]),
            timestamp=str(row["startTime"]),
            agents=row["agents"],
            llms=[],
            tokens=row["tokens"],
            status=TASK_STATUS_DONE,
            cost=row["cost"] or 0.0,
            duration=row["duration"] or 0.0,
        )
        session_list.append(session_item)
        total_duration += row["duration"] or 0.0

    avg_duration = (
        float(int(total_duration / len(session_list))) if session_list else 0.0
    )

    return CollectByApplicationResponse(
        avgDuration=avg_duration,
        successRate=100.0,
        errorRate=0.0,
        sessionList=session_list,
    )


def _get_application_sessions_with_stateful_eval_multiquery(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    start_time: str = "",
    end_time: str = "",
    get_session_metrics_fn: Callable | None = None,
) -> CollectByApplicationResponse:
    """Return collect-by-application data for an application, including a
    session-attached stateful evaluation metric (e.g. `trajectory_score`).

    For Neo4j this performs a single Cypher query that returns both the
    session aggregates and any attached Metric nodes matching
    `trajectory_score` / `statefulEval`.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    start_dt = epoch_to_dt_str(start_epoch)
    end_dt = epoch_to_dt_str(end_epoch)

    sessions_stmt = (
        ui_queries.collect_page_sessions_with_stateful_eval_query_multi_query(
            dialect=Dialect.NEO4J,
            start_time=start_dt,
            end_time=end_dt,
            application_id=application_id,
        )
    )
    try:
        # Query builders may return either a bare query string or a (query, params)
        # tuple for drivers that support parameters (Neo4j). Handle both.
        if isinstance(sessions_stmt, tuple):
            query, params = sessions_stmt
            rows = db.execute(query, params)
        else:
            rows = db.execute(sessions_stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get application sessions for '{application_id}': {exc}"
        ) from exc

    if not rows:
        return CollectByApplicationResponse()

    session_list: list[CollectSessionItem] = []
    total_duration = 0.0

    for row in rows:
        # statefulEvals is a collected list (possibly empty); pick first entry
        stateful = None
        evals = row.get("statefulEvals") or []
        if isinstance(evals, (list, tuple)) and evals:
            first = evals[0]
            # normalize to a dict with expected keys
            if isinstance(first, dict) and first.get("name"):
                stateful = {
                    "name": first.get("name"),
                    "value": first.get("result")
                    if first.get("result") is not None
                    else first.get("value"),
                    "metric_id": first.get("metric_id"),
                    "source": first.get("source"),
                    "reasoning": first.get("reasoning"),
                }

        session_metrics: list[dict] = []
        session_id = str(row["sessionId"])
        if get_session_metrics_fn is not None:
            try:
                session_metrics_response = get_session_metrics_fn(session_id)
                session_metrics = [
                    metric.model_dump()
                    for metric in (session_metrics_response.metrics or [])
                ]
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning(
                    "Failed to get session metrics for session_id=%s: %s",
                    session_id,
                    exc,
                )

        session_item = CollectSessionItem(
            sessionId=session_id,
            timestamp=str(row["startTime"]),
            agents=row.get("agents") or [],
            llms=[],
            tokens=row.get("tokens") or 0,
            status=TASK_STATUS_DONE,
            cost=row.get("cost") or 0.0,
            duration=row.get("duration") or 0.0,
            session_metrics=session_metrics,
            statefulEval=stateful,
        )
        session_list.append(session_item)
        total_duration += row.get("duration") or 0.0

    avg_duration = (
        float(int(total_duration / len(session_list))) if session_list else 0.0
    )

    return CollectByApplicationResponse(
        avgDuration=avg_duration,
        successRate=100.0,
        errorRate=0.0,
        sessionList=session_list,
    )


def _parse_metric_result_single_query(
    raw_result: object,
) -> tuple[float | None, str | None, str | None, str | None]:
    """Parse stored metric payload for single-query session metric mapping."""
    if raw_result is None:
        return None, None, None, None

    if isinstance(raw_result, Real) and not isinstance(raw_result, bool):
        return float(raw_result), None, None, None

    parsed = raw_result
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
        except (json.JSONDecodeError, TypeError):
            return None, None, None, None

    if isinstance(parsed, Real) and not isinstance(parsed, bool):
        return float(parsed), None, None, None

    if not isinstance(parsed, dict):
        return None, None, None, None

    value = parsed.get("value")
    parsed_value = (
        float(value)
        if isinstance(value, Real) and not isinstance(value, bool)
        else None
    )
    return (
        parsed_value,
        parsed.get("metric_id"),
        parsed.get("source"),
        parsed.get("reasoning"),
    )


def _build_session_metrics_single_query(
    raw_metrics: object,
) -> list[dict[str, object]]:
    """Map raw metric dictionaries to MetricItem-compatible dictionaries."""
    if not isinstance(raw_metrics, (list, tuple)):
        return []

    session_metrics: list[dict[str, object]] = []
    for metric in raw_metrics:
        if not isinstance(metric, dict):
            continue

        name = metric.get("name")
        if not name:
            continue

        value, metric_id, source, reasoning = _parse_metric_result_single_query(
            metric.get("result")
        )
        if value is None:
            raw_value = metric.get("value")
            if isinstance(raw_value, Real) and not isinstance(raw_value, bool):
                value = float(raw_value)

        if metric_id is None:
            metric_id = metric.get("metric_id") or name
        if source is None:
            source = metric.get("source")
        if reasoning is None:
            reasoning = metric.get("reasoning")

        provider = metric.get("provider") or source or "oxp"

        session_metrics.append(
            {
                "name": name,
                "value": value,
                "metric_id": metric_id,
                "source": source or provider,
                "reasoning": reasoning,
                "error": None,
            }
        )

    return session_metrics


def _get_application_sessions_with_stateful_eval(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    start_time: str = "",
    end_time: str = "",
    semantic_group_id: str = "",
) -> CollectByApplicationResponse:
    """Return collect-by-application data using a single query.

    This variant returns sessions, stateful eval, and session metrics in one
    Neo4j query without per-session metric lookups.
    """
    start_epoch, end_epoch = parse_epoch_range(start_time, end_time)

    if start_epoch > end_epoch:
        raise ValueError("invalid time range")

    # Session.startTime is stored in Neo4j as a float Unix epoch (seconds), so
    # the time bounds must be passed as numeric epochs — formatting them as
    # datetime strings would make the Cypher comparison (float >= string) yield
    # null and silently drop every session.
    sessions_stmt = ui_queries.collect_page_sessions_with_stateful_eval_query(
        dialect=Dialect.NEO4J,
        start_time=start_epoch,
        end_time=end_epoch,
        application_id=application_id,
        semantic_group_id=semantic_group_id or None,
    )
    try:
        if isinstance(sessions_stmt, tuple):
            query, params = sessions_stmt
            rows = db.execute(query, params)
        else:
            rows = db.execute(sessions_stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get application sessions for '{application_id}': {exc}"
        ) from exc

    if not rows:
        return CollectByApplicationResponse()

    session_list: list[CollectSessionItem] = []
    total_duration = 0.0

    for row in rows:
        stateful = None
        evals = row.get("statefulEvals") or []
        if isinstance(evals, (list, tuple)) and evals:
            first = evals[0]
            if isinstance(first, dict) and first.get("name"):
                stateful = {
                    "name": first.get("name"),
                    "value": first.get("result")
                    if first.get("result") is not None
                    else first.get("value"),
                    "metric_id": first.get("metric_id"),
                    "source": first.get("source"),
                    "reasoning": first.get("reasoning"),
                }

        session_item = CollectSessionItem(
            sessionId=str(row["sessionId"]),
            timestamp=str(row["startTime"]),
            agents=row.get("agents") or [],
            llms=[],
            tokens=row.get("tokens") or 0,
            status=TASK_STATUS_DONE,
            cost=row.get("cost") or 0.0,
            duration=row.get("duration") or 0.0,
            session_metrics=_build_session_metrics_single_query(
                row.get("sessionMetrics")
            ),
            statefulEval=stateful,
        )
        session_list.append(session_item)
        total_duration += row.get("duration") or 0.0

    avg_duration = (
        float(int(total_duration / len(session_list))) if session_list else 0.0
    )

    return CollectByApplicationResponse(
        avgDuration=avg_duration,
        successRate=100.0,
        errorRate=0.0,
        sessionList=session_list,
    )


# ── get_application_topology ─────────────────────────────────────────────────


def _get_application_topology(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
) -> dict:
    """Return topology data from graph spans for *application_id*."""
    import json

    stmt = ui_queries.topology_query(dialect, application_id=application_id)
    try:
        rows = db.execute(stmt)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get topology for application '{application_id}': {exc}"
        ) from exc

    if not rows or not rows[0][0]:
        return {}

    raw = rows[0][0]

    if dialect is Dialect.SQLITE:
        # SQLite: full SpanAttributes dict stored as string
        attrs = parse_span_attributes(str(raw))
        graph_str = attrs.get("gen_ai.ioa.graph", "")
    else:
        # ClickHouse: query already extracted the key as a string
        graph_str = str(raw)

    try:
        graph = json.loads(graph_str)
    except (json.JSONDecodeError, TypeError):
        return {}

    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            data = node.get("data")
            if isinstance(data, str) and "StructuredTool(" in data:
                node["data"] = parse_tools_from_repr(data)

    # Attach agent descriptions from agent_start_event spans
    session_id = str(rows[0][1]) if len(rows[0]) > 1 and rows[0][1] else ""
    if session_id and isinstance(nodes, dict):
        desc_stmt = ui_queries.agent_descriptions_by_application_query(
            dialect,
            application_id=application_id,
            session_id=session_id,
        )
        try:
            desc_rows = db.execute(desc_stmt)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get agent descriptions for application '{application_id}': {exc}"
            ) from exc

        # Build agent_name → description map from all agent_start_event rows
        agent_descs: dict[str, str] = {}
        for drow in desc_rows:
            raw = drow[0]
            if isinstance(raw, list):
                # clickhouse-connect may return Array(Map(...)) as native list
                events = raw
            else:
                raw_events = str(raw) if raw else ""
                events = parse_events_attributes(raw_events)
            for evt in events:
                a_name = evt.get("agent_name", "")
                desc = evt.get("description", "")
                if a_name and desc:
                    agent_descs[a_name] = desc
                    # Also store by base name (before dot)
                    base = a_name.split(".")[0]
                    if base not in agent_descs:
                        agent_descs[base] = desc

        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            node_id = node.get("id", "")
            node_name = node.get("name", "")
            # Skip nodes that already have tool data
            if isinstance(node.get("data"), list):
                continue
            # Match node id/name against known agent names
            desc = agent_descs.get(node_id) or agent_descs.get(node_name) or ""
            if desc:
                node["description"] = desc

    return graph


def _get_application_semanticgroups(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    only_leaf_nodes: bool = False,
) -> SemanticgroupsResponse:
    """Return semantic group nodes for an application.

    When ``only_leaf_nodes`` is true, only leaf nodes are returned using the table
    semantic-group query; otherwise all semantic-group nodes are returned.
    """
    if only_leaf_nodes:
        stmt, params = ui_queries.semantic_groups_table_query(
            dialect,
            application_id=application_id,
        )
    else:
        stmt, params = ui_queries.semantic_groups_query(
            dialect,
            application_id=application_id,
        )

    try:
        rows = db.execute(stmt, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get semantic groups for application '{application_id}': {exc}"
        ) from exc

    nodes: list[SemanticGroupNode] = []
    for row in rows:
        raw_node = None
        if isinstance(row, dict):
            raw_node = row.get("sg") if "sg" in row else row
        elif isinstance(row, (list, tuple)) and row:
            raw_node = row[0]

        # neo4j.graph.Node stores properties under _properties.
        if hasattr(raw_node, "_properties"):
            raw_node = getattr(raw_node, "_properties")

        if not isinstance(raw_node, dict):
            continue
        nodes.append(
            SemanticGroupNode(
                id=str(raw_node.get(SEMANTICGROUP_NODE_ID) or ""),
                group_name=str(raw_node.get(SEMANTICGROUP_NODE_GROUP_NAME) or ""),
                group_summary=str(raw_node.get(SEMANTICGROUP_NODE_GROUP_SUMMARY) or ""),
                n_sessions=int(raw_node.get(SEMANTICGROUP_NODE_N_SESSIONS) or 0),
                medioid_session_id=str(
                    raw_node.get(SEMANTICGROUP_NODE_MEDIOID_SESSION_ID) or ""
                ),
                children_nodes=[
                    str(v)
                    for v in (raw_node.get(SEMANTICGROUP_NODE_CHILDREN_NODES) or [])
                ],
                session_ids=[
                    str(v) for v in (raw_node.get(SEMANTICGROUP_NODE_SESSION_IDS) or [])
                ],
                split_distance=float(
                    raw_node.get(SEMANTICGROUP_NODE_SPLIT_DISTANCE) or 0.0
                ),
                overall_quality=float(
                    row.get(SEMANTICGROUP_NODE_OVERALL_QUALITY) or 0.0
                ),
                overall_reliability=float(
                    row.get(SEMANTICGROUP_NODE_OVERALL_RELIABILITY) or 0.0
                ),
                overall_performance=float(
                    row.get(SEMANTICGROUP_NODE_OVERALL_PERFORMANCE) or 0.0
                ),
            )
        )

    return SemanticgroupsResponse(nodes=nodes)


def _get_application_semanticgroup_impact_assessment(
    db: Connector,
    dialect: Dialect,
    *,
    application_id: str,
    semanticgroup_id: str,
    start_time: str = "",
    end_time: str = "",
) -> ImpactAssessmentResponse:
    """Return impact assessment for a semantic group."""

    import json

    stmt, params = ui_queries.semantic_group_impact_assessment_query(
        dialect,
        application_id=application_id,
        semanticgroup_id=semanticgroup_id,
    )

    try:
        rows = db.execute(stmt, params)
    except Exception as exc:
        raise DatabaseError(
            f"Failed to get impact assessment for semantic group '{semanticgroup_id}' in application '{application_id}': {exc}"
        ) from exc

    impact_report: list[ImpactAssessmentMetric] = []

    for row in rows:
        metric_name = str(row.get("metricName") or "")
        contrib = row.get("contributions") or ""
        if metric_name and contrib:
            agents = []
            for item in contrib:
                try:
                    if isinstance(item, str):
                        item = json.loads(item)
                except json.JSONDecodeError as e:
                    logger.error(
                        "Failed to parse contribution item as JSON: %s - %s", item, e
                    )
                    continue
                agent_name = item.get("agent", "")
                if agent_name:
                    agents.append(
                        ImpactAssementAgentItem(
                            agent_name=agent_name,
                            value=SingleValueData(
                                value=float(item.get("value", 0.0)), unit="PERCENTAGE"
                            ),
                        )
                    )
            impact_report.append(
                ImpactAssessmentMetric(metric_name=metric_name, agents=agents)
            )
    return ImpactAssessmentResponse(impact_report=impact_report)
