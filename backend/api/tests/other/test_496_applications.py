#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Functional test for applications endpoint using a real ClickHouse DB.

Run with:
    pytest tests/test_496_applications.py -v -s
"""

import logging
import os
import sys

import fakeredis
import pytest
from fastapi.testclient import TestClient
from dotenv import load_dotenv

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.client import LocalClient
from oxp.connectors.clickhouse import ClickHouseConnector
from oxp.connectors.neo4j import Neo4JConnector
from oxp.dependencies import get_db, get_redis

# Load .env for test-only environment defaults.
load_dotenv()

logger = logging.getLogger(__name__)

# Ensure the project root is on sys.path so "oxp" is importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Module-scoped ClickHouse connector (shared across all tests).
_connector: ClickHouseConnector | None = None
_neo4j_connector: Neo4JConnector | None = None


def export_llmcall_tokens_to_excel(
    output_file: str | None = None,
    session_ids: list[str] | None = None,
    mas_name: str | None = None,
) -> str:
    """Run the LLMCall token query and export the rows to an Excel file.

    Returns the absolute output path.
    """
    from openpyxl import Workbook
    from openpyxl.utils.cell import get_column_letter

    if not session_ids:
        raise ValueError("session_ids must be provided")

    connector = _get_neo4j_connector()

    query = """
        MATCH (lc:LLMCall)
        WHERE lc.sessionId IN $session_ids
        OPTIONAL MATCH (s:Session {sessionId: lc.sessionId})-[]-(ma:MAS)
        WITH lc,
             [name IN collect(DISTINCT ma.masName)
              WHERE name IS NOT NULL
                AND name <> ''
                AND ($mas_name IS NULL OR name = $mas_name)] AS mas_names
        RETURN
        lc.sessionId AS session_id,
        lc.spanId AS spanId,
        lc.promptTokenCount AS promptTokenCount,
        lc.completionTokenCount AS completionTokenCount,
        lc.totalTokenCount AS totalTokenCount,
        coalesce(toFloat(lc.promptTokenCount), 0.0)
            + coalesce(toFloat(lc.completionTokenCount), 0.0) AS computedTotalTokens,
        lc.llmName AS llmName,
        lc.modelName AS modelName,
        lc.name AS name,
        CASE WHEN size(mas_names) > 0 THEN mas_names[0] ELSE '' END AS masName
        ORDER BY session_id
    """

    rows = connector.execute(
        query,
        {"session_ids": session_ids, "mas_name": mas_name},
    )

    columns = [
        "session_id",
        "spanId",
        "promptTokenCount",
        "completionTokenCount",
        "totalTokenCount",
        "computedTotalTokens",
        "llmName",
        "modelName",
        "name",
        "masNameFromLlmQuery",
        "masNameFromCostQuery",
        "mas_cost_sum",
        "expected_cost_from_tokens",
        "expected_cost_formula",
    ]

    prompt_cost_per_token = 1e-5
    completion_cost_per_token = 3e-5

    expected_cost_formula = "(promptTokenCount x 1e-5) + (completionTokenCount x 3e-5)"

    if output_file is None:
        output_file = os.path.join(
            os.path.dirname(__file__),
            "logs",
            "llmcall_tokens.xlsx",
        )
    output_file = os.path.abspath(output_file)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    wb = Workbook()
    by_application: dict[str, list[list[object]]] = {}
    for row in rows:
        llm_mas_name = str(row.get("masName") or "")
        application_name = llm_mas_name if llm_mas_name else "unknown_application"
        try:
            prompt_tokens = float(row.get("promptTokenCount") or 0.0)
        except (TypeError, ValueError):
            prompt_tokens = 0.0
        try:
            completion_tokens = float(row.get("completionTokenCount") or 0.0)
        except (TypeError, ValueError):
            completion_tokens = 0.0
        expected_cost = (prompt_tokens * prompt_cost_per_token) + (
            completion_tokens * completion_cost_per_token
        )
        by_application.setdefault(application_name, []).append(
            [
                row.get("session_id"),
                row.get("spanId"),
                row.get("promptTokenCount"),
                row.get("completionTokenCount"),
                row.get("totalTokenCount"),
                row.get("computedTotalTokens"),
                row.get("llmName"),
                row.get("modelName"),
                row.get("name"),
                llm_mas_name,
                llm_mas_name,
                0.0,
                expected_cost,
                expected_cost_formula,
            ]
        )

    # Remove the default sheet and create one sheet per application.
    wb.remove(wb.active)

    def _safe_sheet_title(name: str) -> str:
        invalid_chars = set("[]:*?/\\")
        sanitized = "".join("_" if c in invalid_chars else c for c in name).strip()
        if not sanitized:
            sanitized = "unknown_application"
        return sanitized[:31]

    def _append_totals_row(ws) -> None:
        # Add a totals row at the bottom for numeric columns.
        last_data_row = ws.max_row
        totals_row = [""] * len(columns)
        totals_row[0] = "TOTAL"
        if last_data_row >= 2:
            summable_columns = [
                "promptTokenCount",
                "completionTokenCount",
                "totalTokenCount",
                "computedTotalTokens",
                "mas_cost_sum",
                "expected_cost_from_tokens",
            ]
            for column_name in summable_columns:
                col_index = columns.index(column_name) + 1
                col_letter = get_column_letter(col_index)
                totals_row[col_index - 1] = (
                    f"=SUM({col_letter}2:{col_letter}{last_data_row})"
                )
        ws.append(totals_row)

    def _to_float(value: object) -> float:
        if value is None or value == "":
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _get_mas_cost_sum(
        connector: Neo4JConnector,
        current_mas_name: str,
        session_id: str,
        cache: dict[tuple[str, str], float],
    ) -> float:
        cache_key = (current_mas_name, session_id)
        if cache_key in cache:
            return cache[cache_key]

        if not current_mas_name or not session_id:
            cache[cache_key] = 0.0
            return 0.0

        cost_query = """
            MATCH (m:MAS {masName: $mas_name})-[]-(s:Session {sessionId: $session_id})-[]-(me:Metric {metricName: "Cost"})
            RETURN coalesce(SUM(toFloat(me.value)), 0.0) AS mas_cost_sum
        """
        cost_rows = connector.execute(
            cost_query,
            {"mas_name": current_mas_name, "session_id": session_id},
        )
        value = 0.0
        if cost_rows:
            value = _to_float(cost_rows[0].get("mas_cost_sum"))
        cache[cache_key] = value
        return value

    if not by_application:
        ws = wb.create_sheet("llmcall_tokens")
        ws.append(columns)
        _append_totals_row(ws)
    else:
        used_titles: set[str] = set()
        summary_cost_cache: dict[tuple[str, str], float] = {}

        def _unique_sheet_title(raw_name: str) -> str:
            base_title = _safe_sheet_title(raw_name)
            title = base_title
            suffix = 1
            while title in used_titles:
                trailer = f"_{suffix}"
                title = f"{base_title[: 31 - len(trailer)]}{trailer}"
                suffix += 1
            used_titles.add(title)
            return title

        for application_name in sorted(by_application):
            title = _unique_sheet_title(application_name)

            ws = wb.create_sheet(title)
            ws.append(columns)
            for row_values in by_application[application_name]:
                ws.append(row_values)
            _append_totals_row(ws)

            # Add a per-application summary sheet with one row per session.
            summary_title = _unique_sheet_title(f"{application_name}_summary")
            ws_summary = wb.create_sheet(summary_title)
            ws_summary.append(columns)

            session_agg: dict[str, dict[str, object]] = {}
            for row_values in by_application[application_name]:
                sid = str(row_values[0] or "")
                if sid not in session_agg:
                    session_agg[sid] = {
                        "prompt": 0.0,
                        "completion": 0.0,
                        "total": 0.0,
                        "computed": 0.0,
                        "llms": set(),
                        "models": set(),
                        "names": set(),
                        "mas": str(row_values[9] or ""),
                    }

                bucket = session_agg[sid]
                bucket["prompt"] = float(bucket["prompt"]) + _to_float(row_values[2])
                bucket["completion"] = float(bucket["completion"]) + _to_float(
                    row_values[3]
                )
                bucket["total"] = float(bucket["total"]) + _to_float(row_values[4])
                bucket["computed"] = float(bucket["computed"]) + _to_float(
                    row_values[5]
                )
                if row_values[6]:
                    bucket["llms"].add(str(row_values[6]))
                if row_values[7]:
                    bucket["models"].add(str(row_values[7]))
                if row_values[8]:
                    bucket["names"].add(str(row_values[8]))

            for sid in sorted(session_agg):
                bucket = session_agg[sid]
                llm_names = ",".join(sorted(bucket["llms"]))
                model_names = ",".join(sorted(bucket["models"]))
                call_names = ",".join(sorted(bucket["names"]))
                mas_value = str(bucket["mas"] or "")
                mas_cost_sum = _get_mas_cost_sum(
                    connector,
                    mas_value or application_name,
                    sid,
                    summary_cost_cache,
                )

                ws_summary.append(
                    [
                        sid,
                        "",
                        bucket["prompt"],
                        bucket["completion"],
                        bucket["total"],
                        bucket["computed"],
                        llm_names,
                        model_names,
                        call_names,
                        mas_value,
                        mas_value,
                        mas_cost_sum,
                        (
                            (float(bucket["prompt"]) * prompt_cost_per_token)
                            + (float(bucket["completion"]) * completion_cost_per_token)
                        ),
                        expected_cost_formula,
                    ]
                )
            _append_totals_row(ws_summary)

    wb.save(output_file)
    logger.info("Exported %s rows to %s", len(rows), output_file)
    return output_file


def _get_connector() -> ClickHouseConnector:
    """Lazily create a module-level ClickHouse connector."""
    global _connector  # noqa: PLW0603
    if _connector is None:
        host = os.environ.get("CLICKHOUSE_HOST") or "localhost"
        port = int(os.environ.get("CLICKHOUSE_PORT") or "8123")
        username = os.environ.get("CLICKHOUSE_USERNAME") or "default"
        password = os.environ.get("CLICKHOUSE_PASSWORD") or ""
        database = os.environ.get("CLICKHOUSE_DATABASE") or "default"
        _connector = ClickHouseConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
        _connector.connect()
        logger.info(
            "Using ClickHouse connector - %s:%s/%s",
            host,
            port,
            database,
        )
    return _connector


def _get_neo4j_connector() -> Neo4JConnector:
    """Lazily create a module-level Neo4j connector."""
    global _neo4j_connector  # noqa: PLW0603
    if _neo4j_connector is None:
        host = os.environ.get("NEO4J_HOST") or "localhost"
        port = int(os.environ.get("NEO4J_PORT") or "7687")
        username = os.environ.get("NEO4J_USERNAME") or "neo4j"
        password = os.environ.get("NEO4J_PASSWORD") or ""
        database = os.environ.get("NEO4J_DATABASE") or "neo4j"
        _neo4j_connector = Neo4JConnector(
            host=host,
            port=port,
            username=username,
            password=password,
            database=database,
        )
        _neo4j_connector.connect()
        logger.info(
            "Using Neo4J connector - %s:%s/%s",
            host,
            port,
            database,
        )
    return _neo4j_connector


@pytest.fixture(autouse=True, scope="module")
def _bootstrap():
    """Initialize the ClickHouse connector once for the module and clean up after."""
    conn = _get_connector()
    reset_client()
    yield
    conn.close()


@pytest.fixture()
def local_db():
    """Provide the shared ClickHouse connector for tests."""
    return _get_connector()


@pytest.fixture()
def neo4j_db():
    """Provide a shared Neo4j connector, skipping test when unavailable."""
    try:
        return _get_neo4j_connector()
    except Exception as exc:  # pragma: no cover - depends on local env
        pytest.skip(f"Neo4j unavailable for test: {exc}")


@pytest.fixture()
def client(local_db):
    """Return a FastAPI TestClient with DB and Redis dependency overrides."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_db] = lambda: local_db
    app.dependency_overrides[get_redis] = lambda: fake_redis
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_redis, None)
    reset_client()


BASE = "/api/v1"


class TestLocalClientInstance:
    """Verify /ui/applications returns real data from ClickHouse."""

    @staticmethod
    def _normalize_applications_payload(payload: dict) -> dict:
        normalized_apps = []
        for app_item in payload.get("applications", []):
            item = dict(app_item)
            if isinstance(item.get("llms"), list):
                item["llms"] = sorted(item["llms"])
            if isinstance(item.get("agents"), list):
                item["agents"] = sorted(item["agents"])
            normalized_apps.append(item)

        normalized_apps.sort(
            key=lambda app: (
                app.get("applicationName", ""),
                app.get("version", 0),
                app.get("timestamp", ""),
            )
        )
        return {"applications": normalized_apps}

    def test_get_applications_from_clickhouse(self, local_db, client) -> None:
        app_limit = 10
        app_offset = 0

        # Use the real local client result as the expected payload.
        c = LocalClient(db=local_db)
        expected = c.get_applications_from_clickhouse(
            limit=app_limit, offset=app_offset
        )

        result_http = client.get(
            f"{BASE}/ui/applications-from-clickhouse",
            params={
                "limit": app_limit,
                "offset": app_offset,
            },
        )
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info("HTTP /api/v1/ui/applications-from-clickhouse response: %s", data)

        assert "applications" in data
        assert isinstance(data["applications"], list)
        assert self._normalize_applications_payload(
            data
        ) == self._normalize_applications_payload(expected.model_dump())

    def test_get_applications_from_clickhouse_multiquery(
        self, local_db, client
    ) -> None:
        app_limit = 10
        app_offset = 0

        # Use the real local client result as the expected payload.
        c = LocalClient(db=local_db)
        expected = c.get_applications_from_clickhouse_multiquery(
            limit=app_limit,
            offset=app_offset,
        )

        result_http = client.get(
            f"{BASE}/ui/applications-from-clickhouse-optimized",
            params={
                "limit": app_limit,
                "offset": app_offset,
            },
        )
        assert result_http.status_code == 200

        data = result_http.json()
        logger.info(
            "HTTP /api/v1/ui/applications-from-clickhouse-optimized response: %s", data
        )

        assert "applications" in data
        assert isinstance(data["applications"], list)
        assert self._normalize_applications_payload(
            data
        ) == self._normalize_applications_payload(expected.model_dump())

    def test_get_applications(self, neo4j_db) -> None:
        app_limit = 10
        app_offset = 0

        c = LocalClient(db=neo4j_db)
        result = c.get_applications(limit=app_limit, offset=app_offset)

        payload = result.model_dump()
        logger.info("LocalClient.get_applications response: %s", payload)

        assert "applications" in payload
        assert isinstance(payload["applications"], list)
        for app_item in payload["applications"]:
            assert "applicationName" in app_item
            assert "cost" in app_item
            assert "costDollars" in app_item
            assert "llms" in app_item
            assert "agents" in app_item
            assert "overallPerformance" in app_item

    def test_get_applications_verification(self, neo4j_db) -> None:
        """Verify that get_applications and get_applications_multiquery return the same data."""
        app_limit = 10
        app_offset = 0

        c = LocalClient(db=neo4j_db)

        result = c.get_applications(limit=app_limit, offset=app_offset)

        payload = result.model_dump()

        assert "applications" in payload
        assert isinstance(payload["applications"], list)
        for app_item in payload["applications"]:
            assert "applicationName" in app_item
            assert "cost" in app_item
            assert "costDollars" in app_item
            assert "llms" in app_item
            assert "agents" in app_item
            assert "overallPerformance" in app_item

        result_multiquery = c.get_applications_multiquery(
            limit=app_limit, offset=app_offset
        )

        payload_multiquery = result_multiquery.model_dump()

        assert "applications" in payload_multiquery
        assert isinstance(payload_multiquery["applications"], list)
        for app_item in payload_multiquery["applications"]:
            assert "applicationName" in app_item
            assert "cost" in app_item
            assert "costDollars" in app_item
            assert "llms" in app_item
            assert "agents" in app_item
            assert "overallPerformance" in app_item

        logger.info("LocalClient.get_applications response: %s", payload)
        logger.info(
            "LocalClient.get_applications_multiquery response: %s", payload_multiquery
        )

        assert self._normalize_applications_payload(
            payload
        ) == self._normalize_applications_payload(payload_multiquery)

    def test_get_applications_debug_cost(self, neo4j_db) -> None:
        app_limit = 10
        app_offset = 0

        c = LocalClient(db=neo4j_db)
        result = c.get_applications(limit=app_limit, offset=app_offset)

        payload = result.model_dump()
        logger.info("LocalClient.get_applications response: %s", payload)

        assert "applications" in payload
        assert isinstance(payload["applications"], list)
        for app_item in payload["applications"]:
            assert "applicationName" in app_item
            assert "cost" in app_item
            assert "costDollars" in app_item
            assert "llms" in app_item
            assert "agents" in app_item
            assert "overallPerformance" in app_item

        application_names = sorted(
            {
                str(app_item.get("applicationName"))
                for app_item in payload["applications"]
                if app_item.get("applicationName")
            }
        )
        if not application_names:
            pytest.skip("No applications available to export LLMCall tokens")

        session_rows = neo4j_db.execute(
            """
            MATCH (s:Session)-[]-(ma:MAS)
            WHERE ma.masName IN $application_names
              AND s.sessionId IS NOT NULL
            RETURN DISTINCT s.sessionId AS sid
            """,
            {"application_names": application_names},
        )
        session_ids = sorted(str(r.get("sid")) for r in session_rows if r.get("sid"))
        if not session_ids:
            pytest.skip("No sessions found for retrieved applications")

        export_path = export_llmcall_tokens_to_excel(
            output_file=os.path.join(
                os.path.dirname(__file__),
                "logs",
                "llmcall_tokens_all_applications.xlsx",
            ),
            session_ids=session_ids,
        )
        logger.info(
            "Exported all-applications LLMCall token rows to %s (applications=%s, sessions=%s)",
            export_path,
            len(application_names),
            len(session_ids),
        )

    def test_get_applications_debug(self, neo4j_db) -> None:
        app_limit = 10
        app_offset = 0
        application_name = "noa-trip-planner-mas"

        # Find a compact time window with <5 sessions to simplify manual debugging.
        rows = neo4j_db.execute(
            """
            MATCH (s:Session)-[]-(ma:MAS)
            WHERE ma.masName IS NOT NULL
              AND ma.masName <> ''
                            AND ma.masName = $application_name
              AND s.sessionId IS NOT NULL
              AND s.startTime IS NOT NULL
            RETURN DISTINCT s.sessionId AS sid, toFloat(s.startTime) AS ts
            ORDER BY ts DESC
            LIMIT 1000
                        """,
            {"application_name": application_name},
        )

        session_points = [
            (str(r.get("sid")), float(r.get("ts")))
            for r in rows
            if r.get("sid") and r.get("ts") is not None
        ]
        if not session_points:
            pytest.skip("No Neo4j sessions available for debug time-slot selection")

        slot_start: float | None = None
        slot_end: float | None = None
        slot_session_ids: list[str] = []

        # Try increasingly wider windows around each session timestamp.
        for half_window in (0.0, 5.0, 15.0, 30.0, 60.0, 120.0):
            for _, center_ts in session_points:
                start = center_ts - half_window
                end = center_ts + half_window
                sids = sorted(
                    {sid for sid, ts in session_points if ts >= start and ts <= end}
                )
                if 0 < len(sids) < 5:
                    slot_start = start
                    slot_end = end
                    slot_session_ids = sids
                    break
            if slot_start is not None:
                break

        if slot_start is None or slot_end is None:
            pytest.skip(
                "Could not find a debug time slot with fewer than 5 sessions "
                f"for application '{application_name}'"
            )

        logger.info(
            "Debug slot selected: start=%s end=%s sessions=%s ids=%s",
            slot_start,
            slot_end,
            len(slot_session_ids),
            slot_session_ids,
        )

        c = LocalClient(db=neo4j_db)
        result = c.get_applications(
            start_time=str(slot_start),
            end_time=str(slot_end),
            limit=app_limit,
            offset=app_offset,
        )

        payload = result.model_dump()
        logger.info("LocalClient.get_applications response: %s", payload)

        assert "applications" in payload
        assert isinstance(payload["applications"], list)
        for app_item in payload["applications"]:
            assert "applicationName" in app_item
            assert app_item["applicationName"] == application_name
            assert "cost" in app_item
            assert "costDollars" in app_item
            assert "llms" in app_item
            assert "agents" in app_item
            assert "overallPerformance" in app_item

    def test_get_applications_multiquery(self, neo4j_db) -> None:
        app_limit = 10
        app_offset = 0

        c = LocalClient(db=neo4j_db)
        result = c.get_applications_multiquery(limit=app_limit, offset=app_offset)

        payload = result.model_dump()
        logger.info("LocalClient.get_applications_multiquery response: %s", payload)

        assert "applications" in payload
        assert isinstance(payload["applications"], list)
        for app_item in payload["applications"]:
            assert "applicationName" in app_item
            assert "cost" in app_item
            assert "costDollars" in app_item
            assert "llms" in app_item
            assert "agents" in app_item
            assert "overallPerformance" in app_item
