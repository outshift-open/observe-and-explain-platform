#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from pprint import pformat

from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.connectors.base import Connector
from oxp.dependencies import get_neo4j_db
from oxp.models.otel_traces import SymbolicSessionStateResponse

logger = logging.getLogger(__name__)


class SymbolicStubConnector(Connector):
    def __init__(self) -> None:
        self.commands: list[tuple[str, dict | None]] = []
        self.created_variable_ids: set[str] = set()
        self.models_by_application: dict[str, list[dict[str, object]]] = {
            "app-1": [
                {
                    "modelId": "sm_1",
                    "version": "v1",
                    "createdAt": "2026-01-01T00:00:00Z",
                    "updatedAt": "2026-01-02T00:00:00Z",
                    "isActive": True,
                    "modelName": "claude",
                    "taskDescription": "Route optimization",
                },
                {
                    "modelId": "sm_0",
                    "version": "v0",
                    "createdAt": "2025-12-01T00:00:00Z",
                    "updatedAt": "2025-12-15T00:00:00Z",
                    "isActive": False,
                    "modelName": "claude",
                    "taskDescription": "Legacy route model",
                },
            ]
        }
        self.variables_by_model: dict[str, list[dict[str, object]]] = {
            "sm_1": [
                {
                    "variableId": "route_fare_alignment",
                    "name": "route_fare_alignment",
                    "tier": "alignment",
                    "type": "boolean",
                    "description": "desc",
                    "extractionQuestion": None,
                    "discriminativeScore": None,
                    "isEnabledForEvaluation": None,
                    "foundationMetric": "Groundedness",
                    "status": None,
                    "createdAt": None,
                    "updatedAt": None,
                    "dependsOn": ["fare_information_accessed"],
                },
                {
                    "variableId": "fare_information_accessed",
                    "name": "fare_information_accessed",
                    "tier": "entity",
                    "type": "boolean",
                    "description": "desc",
                    "extractionQuestion": None,
                    "discriminativeScore": None,
                    "isEnabledForEvaluation": None,
                    "status": None,
                    "createdAt": None,
                    "updatedAt": None,
                    "dependsOn": [],
                },
            ],
            "sm_0": [],
        }
        self.session_values_by_session: dict[str, list[dict[str, object]]] = {
            "session-1": [
                {
                    "valueId": "sval_1",
                    "variableId": "route_fare_alignment",
                    "tier": "alignment",
                    "type": "boolean",
                    "value": True,
                    "reason": "covered",
                    "trajectoryIndex": 4,
                    "assignmentStrategy": "aggregate",
                    "createdAt": "2026-01-02T00:00:00Z",
                    "spanId": "span-1",
                }
            ]
        }

    def _models_for_app(self, application_id: str) -> list[dict[str, object]]:
        models = self.models_by_application.get(application_id, [])
        return sorted(
            models,
            key=lambda model: (
                str(model.get("updatedAt") or ""),
                str(model.get("createdAt") or ""),
                str(model.get("modelId") or ""),
            ),
            reverse=True,
        )

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    def execute(self, query, params=None):
        query = str(query)
        params = params or {}

        if "OPTIONAL MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)" in query:
            application_id = params["application_id"]
            active_models = [
                model
                for model in self._models_for_app(application_id)
                if bool(model.get("isActive"))
            ]
            model = active_models[0] if active_models else None
            if model is None:
                return []

            model_id = str(model.get("modelId") or "")
            variables = sorted(
                self.variables_by_model.get(model_id, []),
                key=lambda variable: (
                    str(variable.get("tier") or ""),
                    str(variable.get("name") or ""),
                ),
            )

            if not variables:
                return [
                    {
                        "modelId": model.get("modelId"),
                        "version": model.get("version"),
                        "isActive": model.get("isActive"),
                        "modelName": model.get("modelName"),
                        "taskDescription": model.get("taskDescription"),
                        "variableId": None,
                        "name": None,
                        "tier": None,
                        "type": None,
                        "description": None,
                        "extractionQuestion": None,
                        "discriminativeScore": None,
                        "isEnabledForEvaluation": None,
                        "foundationMetric": None,
                        "status": None,
                        "createdAt": None,
                        "updatedAt": None,
                        "dependsOn": [],
                    }
                ]

            return [
                {
                    "modelId": model.get("modelId"),
                    "version": model.get("version"),
                    "isActive": model.get("isActive"),
                    "modelName": model.get("modelName"),
                    "taskDescription": model.get("taskDescription"),
                    "variableId": variable.get("variableId"),
                    "name": variable.get("name"),
                    "tier": variable.get("tier"),
                    "type": variable.get("type"),
                    "description": variable.get("description"),
                    "extractionQuestion": variable.get("extractionQuestion"),
                    "discriminativeScore": variable.get("discriminativeScore"),
                    "foundationMetric": variable.get("foundationMetric"),
                    "isEnabledForEvaluation": variable.get("isEnabledForEvaluation"),
                    "status": variable.get("status"),
                    "createdAt": variable.get("createdAt"),
                    "updatedAt": variable.get("updatedAt"),
                    "dependsOn": variable.get("dependsOn") or [],
                }
                for variable in variables
            ]

        if (
            "MATCH (mas:MAS {masName: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel"
            in query
            and "OPTIONAL MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)"
            not in query
            and "MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable" not in query
        ):
            rows = self._models_for_app(params["application_id"])
            if "{modelId: $model_id}" in query:
                rows = [row for row in rows if row.get("modelId") == params["model_id"]]
            elif "WHERE coalesce(sm.isActive, false) = true" in query:
                rows = [row for row in rows if bool(row.get("isActive"))]
            if "LIMIT 1" in query:
                rows = rows[:1]
            return rows

        if (
            "MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)"
            in query
            and "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})"
            in query
            and "MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable" not in query
            and "OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]" not in query
        ):
            rows = self._models_for_app("app-1")
            rows = [row for row in rows if row.get("modelId") == params["model_id"]]
            return rows[:1]

        if (
            "MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)"
            in query
            and "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)" in query
            and "OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(value:SymbolicValue)"
            not in query
            and "OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]" not in query
            and "MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable" not in query
        ):
            rows = [
                row
                for row in self._models_for_app("app-1")
                if bool(row.get("isActive"))
            ]
            return rows[:1]

        if "RETURN session.sessionId AS sessionId" in query:
            return [{"sessionId": params["session_id"]}]

        if (
            "MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})"
            in query
        ):
            model_id = str(params.get("model_id") or "")
            existing_variable_ids = {
                str(variable.get("variableId"))
                for variable in self.variables_by_model.get(model_id, [])
                if variable.get("variableId")
            }
            if (
                params["variable_id"] in self.created_variable_ids
                or params["variable_id"] in existing_variable_ids
                or params["variable_id"]
                in {
                    "route_fare_alignment",
                    "fare_information_accessed",
                    "a",
                    "b",
                }
            ):
                return [{"variableId": params["variable_id"]}]
            return []

        if "coalesce(execution.spanId, execution.span_id) = $span_id" in query:
            return [
                {
                    "executionId": "exec_1",
                    "spanId": params["span_id"],
                    "entityName": "planner",
                    "executionLabels": ["LLMCall", "ExecutionElement"],
                }
            ]

        if (
            "OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(value:SymbolicValue)"
            in query
            and "collect({value: value, execution: execution})[0] AS latest" in query
        ):
            return [
                {
                    "modelId": "sm_1",
                    "version": "v1",
                    "isActive": True,
                    "modelName": "claude",
                    "valueId": "sval_1",
                    "variableId": "route_fare_alignment",
                    "tier": "alignment",
                    "type": "boolean",
                    "value": True,
                    "reason": "covered",
                    "trajectoryIndex": 4,
                    "assignmentStrategy": "aggregate",
                    "spanId": "span-1",
                    "entityName": "planner",
                    "executionLabels": ["LLMCall", "ExecutionElement"],
                }
            ]

        if (
            "OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(value:SymbolicValue)"
            in query
            and "collect({value: value, execution: execution})[0] AS latest"
            not in query
        ):
            session_id = params["session_id"]
            model_id = str(params.get("model_id") or "")
            values = self.session_values_by_session.get(session_id, [])
            model = next(
                (
                    row
                    for row in self._models_for_app("app-1")
                    if row.get("modelId") == model_id
                ),
                None,
            )
            if model is None:
                return []

            variable_name_by_id = {
                str(variable.get("variableId")): str(variable.get("name") or "")
                for variable in self.variables_by_model.get(model_id, [])
                if variable.get("variableId")
            }

            if params.get("variable_id"):
                values = [
                    value
                    for value in values
                    if str(value.get("variableId") or "") == str(params["variable_id"])
                ]

            if params.get("variable_name"):
                variable_name = str(params["variable_name"]).lower()
                values = [
                    value
                    for value in values
                    if variable_name_by_id.get(
                        str(value.get("variableId") or "")
                    ).lower()
                    == variable_name
                ]

            values = sorted(
                values,
                key=lambda value: (
                    int(value.get("trajectoryIndex") or -1),
                    str(value.get("createdAt") or ""),
                    str(value.get("valueId") or ""),
                ),
            )

            offset = int(params.get("offset") or 0)
            if offset:
                values = values[offset:]

            if params.get("limit") is not None:
                values = values[: int(params["limit"])]

            return [
                {
                    "modelId": model.get("modelId"),
                    "version": model.get("version"),
                    "modelCreatedAt": model.get("createdAt"),
                    "modelUpdatedAt": model.get("updatedAt"),
                    "isActive": model.get("isActive"),
                    "modelName": model.get("modelName"),
                    "taskDescription": model.get("taskDescription"),
                    "valueId": value.get("valueId"),
                    "variableId": value.get("variableId"),
                    "variableName": variable_name_by_id.get(
                        str(value.get("variableId") or "")
                    ),
                    "tier": value.get("tier"),
                    "type": value.get("type"),
                    "value": value.get("value"),
                    "reason": value.get("reason"),
                    "trajectoryIndex": value.get("trajectoryIndex"),
                    "assignmentStrategy": value.get("assignmentStrategy"),
                    "createdAt": value.get("createdAt"),
                    "executionId": "exec_1",
                    "spanId": value.get("spanId"),
                    "entityName": "planner",
                    "executionLabels": ["LLMCall", "ExecutionElement"],
                }
                for value in values
            ]

        return []

    def execute_command(self, command: str, params=None) -> None:
        self.commands.append((command, params))
        params = params or {}

        if (
            "MERGE (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})"
            in command
        ):
            application_id = params["application_id"]
            model_id = params["model_id"]
            models = self.models_by_application.setdefault(application_id, [])
            if params.get("is_active"):
                for model in models:
                    model["isActive"] = False

            existing = next(
                (model for model in models if model.get("modelId") == model_id), None
            )
            if existing is None:
                models.append(
                    {
                        "modelId": model_id,
                        "version": params.get("version"),
                        "createdAt": params.get("created_at")
                        or params.get("updated_at"),
                        "updatedAt": params.get("updated_at"),
                        "isActive": bool(params.get("is_active")),
                        "modelName": params.get("model_name"),
                        "taskDescription": params.get("task_description"),
                    }
                )
            else:
                existing["version"] = params.get("version")
                existing["updatedAt"] = params.get("updated_at")
                existing["isActive"] = bool(params.get("is_active"))
                existing["modelName"] = params.get("model_name")
                existing["taskDescription"] = params.get("task_description")
                if params.get("created_at") is not None:
                    existing["createdAt"] = params.get("created_at")

        if (
            "MERGE (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})"
            in command
        ):
            self.created_variable_ids.add(params["variable_id"])
            model_id = params["model_id"]
            model_variables = self.variables_by_model.setdefault(model_id, [])
            existing = next(
                (
                    variable
                    for variable in model_variables
                    if variable.get("variableId") == params["variable_id"]
                ),
                None,
            )
            if existing is None:
                model_variables.append(
                    {
                        "variableId": params.get("variable_id"),
                        "name": params.get("name"),
                        "tier": params.get("tier"),
                        "type": params.get("value_type"),
                        "description": params.get("description"),
                        "extractionQuestion": params.get("extraction_question"),
                        "discriminativeScore": params.get("discriminative_score"),
                        "isEnabledForEvaluation": params.get(
                            "is_enabled_for_evaluation"
                        ),
                        "foundationMetric": params.get("foundation_metric"),
                        "status": params.get("status"),
                        "createdAt": params.get("created_at")
                        or params.get("updated_at"),
                        "updatedAt": params.get("updated_at"),
                        "dependsOn": [],
                    }
                )
            else:
                existing["name"] = params.get("name")
                existing["tier"] = params.get("tier")
                existing["type"] = params.get("value_type")
                existing["description"] = params.get("description")
                existing["extractionQuestion"] = params.get("extraction_question")
                existing["discriminativeScore"] = params.get("discriminative_score")
                existing["isEnabledForEvaluation"] = params.get(
                    "is_enabled_for_evaluation"
                )
                existing["foundationMetric"] = params.get("foundation_metric")
                existing["status"] = params.get("status")
                existing["updatedAt"] = params.get("updated_at")
                if params.get("created_at") is not None:
                    existing["createdAt"] = params.get("created_at")

        if "DELETE rel" in command and "DEPENDS_ON" in command:
            model_id = params.get("model_id")
            variable_id = params.get("variable_id")
            if model_id and variable_id:
                model_variables = self.variables_by_model.get(model_id, [])
                for variable in model_variables:
                    if variable.get("variableId") == variable_id:
                        variable["dependsOn"] = []
                        break

        if "MERGE (sv)-[:DEPENDS_ON]->(dep)" in command:
            model_id = params.get("model_id")
            variable_id = params.get("variable_id")
            depends_on_variable_id = params.get("depends_on_variable_id")
            if model_id and variable_id and depends_on_variable_id:
                model_variables = self.variables_by_model.setdefault(model_id, [])
                for variable in model_variables:
                    if variable.get("variableId") == variable_id:
                        depends_on = variable.setdefault("dependsOn", [])
                        if depends_on_variable_id not in depends_on:
                            depends_on.append(depends_on_variable_id)
                        break

        if (
            "MERGE (session)-[:HAS_SYMBOLIC_VALUE]->(symbolicValue:SymbolicValue {valueId: $value_id})"
            in command
        ):
            session_id = params["session_id"]
            values = self.session_values_by_session.setdefault(session_id, [])
            value_id = params["value_id"]
            existing = next(
                (value for value in values if value.get("valueId") == value_id), None
            )
            payload = {
                "valueId": value_id,
                "variableId": params.get("variable_id"),
                "tier": params.get("tier"),
                "type": params.get("value_type"),
                "value": params.get("value"),
                "reason": params.get("reason"),
                "trajectoryIndex": params.get("trajectory_index"),
                "assignmentStrategy": params.get("assignment_strategy"),
                "createdAt": params.get("created_at"),
                "spanId": params.get("span_id"),
            }
            if existing is None:
                values.append(payload)
            else:
                existing.update(payload)


def test_application_variables() -> None:
    connector = SymbolicStubConnector()
    app.dependency_overrides[get_neo4j_db] = lambda: connector
    reset_client()

    try:
        client = TestClient(app)
        new_variable_id = "sv_mock_new_alignment"
        post_response = client.post(
            "/api/v1/symbolic/applications/app-1/variables",
            json={
                "modelId": "sm_1",
                "variables": [
                    {
                        "variableId": new_variable_id,
                        "name": "mock_new_alignment",
                        "tier": "alignment",
                        "type": "boolean",
                        "description": "Inserted by mock integration test",
                        "extractionQuestion": "Is this new variable present?",
                        "discriminativeScore": 0.77,
                        "isEnabledForEvaluation": True,
                        "foundationMetric": "IntentRecognition",
                        "status": "active",
                    }
                ],
                "dependencies": [
                    {
                        "variableId": new_variable_id,
                        "dependsOnVariableId": "fare_information_accessed",
                    }
                ],
            },
        )
        response = client.get("/api/v1/symbolic/applications/app-1/variables")
    finally:
        app.dependency_overrides.pop(get_neo4j_db, None)
        reset_client()

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["written"] >= 1
    assert any(
        variable["variableId"] == "sv_mock_new_alignment"
        for variable in post_payload["variables"]
    )
    assert any(
        variable["variableId"] == "sv_mock_new_alignment"
        and variable["foundationMetric"] == "IntentRecognition"
        for variable in post_payload["variables"]
    )

    assert response.status_code == 200
    payload = response.json()
    logger.debug("get_application_variables response:")
    logger.debug(
        "variables:\n%s",
        pformat(payload["variables"], sort_dicts=False, width=100),
    )
    assert payload["application_id"] == "app-1"
    assert payload["count"] >= 3
    assert any(
        variable["variableId"] == "route_fare_alignment"
        for variable in payload["variables"]
    )
    assert any(
        variable["variableId"] == "sv_mock_new_alignment"
        for variable in payload["variables"]
    )
    assert any(
        variable["variableId"] == "route_fare_alignment"
        and variable["foundationMetric"] == "Groundedness"
        for variable in payload["variables"]
    )


def test_get_session_state() -> None:
    connector = SymbolicStubConnector()
    app.dependency_overrides[get_neo4j_db] = lambda: connector
    reset_client()

    try:
        client = TestClient(app)
        state_response = client.get("/api/v1/symbolic/sessions/session-1/state")
    finally:
        app.dependency_overrides.pop(get_neo4j_db, None)
        reset_client()

    assert state_response.status_code == 200
    state_payload = state_response.json()
    logger.debug("get_session_state response:")
    logger.debug(
        "state_payload:\n%s",
        pformat(state_payload, sort_dicts=False, width=100),
    )
    typed_response = SymbolicSessionStateResponse.model_validate(state_payload)
    assert isinstance(typed_response, SymbolicSessionStateResponse)
    assert typed_response.count == 1
    assert typed_response.state[0].variableId == "route_fare_alignment"


def test_application_models() -> None:
    connector = SymbolicStubConnector()
    app.dependency_overrides[get_neo4j_db] = lambda: connector
    reset_client()

    try:
        client = TestClient(app)
        post_response = client.post(
            "/api/v1/symbolic/applications/app-1/models",
            json={
                "modelId": "sm_2",
                "version": "v2",
                "isActive": True,
                "modelName": "claude-3.7",
                "taskDescription": "Trip planning v2",
                "updatedAt": "2026-02-01T00:00:00Z",
                "createdAt": "2026-02-01T00:00:00Z",
            },
        )
        post_inactive_response_a = client.post(
            "/api/v1/symbolic/applications/app-1/models",
            json={
                "modelId": "sm_3",
                "version": "v3",
                "isActive": False,
                "modelName": "claude-3.7",
                "taskDescription": "Trip planning v3",
                "updatedAt": "2026-03-01T00:00:00Z",
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )
        post_inactive_response_b = client.post(
            "/api/v1/symbolic/applications/app-1/models",
            json={
                "modelId": "sm_4",
                "version": "v4",
                "isActive": False,
                "modelName": "claude-3.7",
                "taskDescription": "Trip planning v4",
                "updatedAt": "2026-03-01T00:00:00Z",
                "createdAt": "2026-04-01T00:00:00Z",
            },
        )
        get_all_response = client.get("/api/v1/symbolic/applications/app-1/models")
        get_active_only_response = client.get(
            "/api/v1/symbolic/applications/app-1/models?activeOnly=true"
        )
        get_latest_response = client.get(
            "/api/v1/symbolic/applications/app-1/models?latest=true"
        )
        get_active_latest_response = client.get(
            "/api/v1/symbolic/applications/app-1/models?activeOnly=true&latest=true"
        )
        get_by_id_response = client.get(
            "/api/v1/symbolic/applications/app-1/models/sm_4"
        )
    finally:
        app.dependency_overrides.pop(get_neo4j_db, None)
        reset_client()

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["written"] == 1
    assert post_payload["symbolic_model"]["modelId"] == "sm_2"
    assert post_payload["symbolic_model"]["isActive"] is True

    assert post_inactive_response_a.status_code == 200
    assert post_inactive_response_b.status_code == 200

    assert get_all_response.status_code == 200
    get_all_payload = get_all_response.json()
    assert get_all_payload["application_id"] == "app-1"
    assert get_all_payload["count"] >= 5
    assert any(model["modelId"] == "sm_2" for model in get_all_payload["models"])
    assert any(model["modelId"] == "sm_4" for model in get_all_payload["models"])
    assert any(not model["isActive"] for model in get_all_payload["models"])
    logger.debug("--------------- get_all_response:")
    logger.debug(
        "models:\n%s",
        pformat(get_all_payload["models"], sort_dicts=False, width=100),
    )

    assert get_active_only_response.status_code == 200
    active_only_payload = get_active_only_response.json()
    assert active_only_payload["application_id"] == "app-1"
    assert active_only_payload["count"] == 1
    assert active_only_payload["models"][0]["modelId"] == "sm_2"
    assert all(model["isActive"] for model in active_only_payload["models"])
    logger.debug("--------------- get_active_only_response:")
    logger.debug(
        "models:\n%s",
        pformat(active_only_payload["models"], sort_dicts=False, width=100),
    )

    assert get_latest_response.status_code == 200
    latest_payload = get_latest_response.json()
    assert latest_payload["count"] == 1
    assert latest_payload["models"][0]["modelId"] == "sm_4"
    logger.debug("--------------- get_latest_response:")
    logger.debug(
        "models:\n%s",
        pformat(latest_payload["models"], sort_dicts=False, width=100),
    )

    assert get_active_latest_response.status_code == 200
    active_latest_payload = get_active_latest_response.json()
    assert active_latest_payload["count"] == 1
    assert active_latest_payload["models"][0]["modelId"] == "sm_2"
    logger.debug("--------------- get_active_latest_response:")
    logger.debug(
        "models:\n%s",
        pformat(active_latest_payload["models"], sort_dicts=False, width=100),
    )

    assert get_by_id_response.status_code == 200
    by_id_payload = get_by_id_response.json()
    assert by_id_payload["application_id"] == "app-1"
    assert by_id_payload["symbolic_model"]["modelId"] == "sm_4"
    logger.debug("--------------- get_by_id_response:")
    logger.debug(
        "models:\n%s",
        pformat(by_id_payload["symbolic_model"], sort_dicts=False, width=100),
    )


def test_session_values() -> None:
    connector = SymbolicStubConnector()
    app.dependency_overrides[get_neo4j_db] = lambda: connector
    reset_client()

    try:
        client = TestClient(app)
        post_response = client.post(
            "/api/v1/symbolic/sessions/session-1/values",
            json={
                "modelId": "sm_1",
                "values": [
                    {
                        "valueId": "sval_new",
                        "variableId": "route_fare_alignment",
                        "tier": "alignment",
                        "type": "boolean",
                        "value": False,
                        "reason": "inconsistent fare mention",
                        "trajectoryIndex": 6,
                        "assignmentStrategy": "single_span",
                        "spanId": "span-2",
                    }
                ],
            },
        )
        get_values_response = client.get("/api/v1/symbolic/sessions/session-1/values")
        get_values_filtered_response = client.get(
            "/api/v1/symbolic/sessions/session-1/values?modelId=sm_1&variableId=route_fare_alignment&limit=1&offset=1"
        )
        get_values_by_name_response = client.get(
            "/api/v1/symbolic/sessions/session-1/values?modelId=sm_1&variableName=route_fare_alignment"
        )
    finally:
        app.dependency_overrides.pop(get_neo4j_db, None)
        reset_client()

    assert post_response.status_code == 200
    assert get_values_response.status_code == 200
    assert get_values_filtered_response.status_code == 200
    assert get_values_by_name_response.status_code == 200

    payload = get_values_response.json()
    logger.debug("test_session_values response:")
    logger.debug(
        "values:\n%s",
        pformat(payload["values"], sort_dicts=False, width=100),
    )
    assert payload["session_id"] == "session-1"
    assert payload["count"] >= 1
    assert any(value["valueId"] == "sval_new" for value in payload["values"])

    filtered_payload = get_values_filtered_response.json()
    assert filtered_payload["symbolic_model"]["modelId"] == "sm_1"
    assert filtered_payload["count"] == 1
    assert filtered_payload["values"][0]["valueId"] == "sval_new"

    by_name_payload = get_values_by_name_response.json()
    assert by_name_payload["count"] >= 1
    assert all(
        value.get("variableName") == "route_fare_alignment"
        for value in by_name_payload["values"]
    )
