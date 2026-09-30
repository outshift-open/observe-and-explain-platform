#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pprint import pformat
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.dependencies import get_neo4j_db

logger = logging.getLogger(__name__)

FLAG_DELETE_TEST_MODELS = os.getenv(
    "FLAG_DELETE_TEST_MODELS", "true"
).strip().lower() in {"1", "true", "yes", "y"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _delete_integration_models_for_application(
    api_client: TestClient, application_id: str
) -> list[str]:
    """Delete all integration models for one application and return deleted ids."""
    get_all_response = api_client.get(
        f"/api/v1/symbolic/applications/{application_id}/models"
    )
    assert get_all_response.status_code == 200
    get_all_payload = get_all_response.json()
    models_to_delete = [
        model["modelId"]
        for model in get_all_payload["models"]
        if isinstance(model.get("modelId"), str)
        and model["modelId"].startswith("sm_integration_")
    ]

    logger.info(
        "FLAG_DELETE_TEST_MODELS enabled: deleting %s integration models for application_id=%s",
        len(models_to_delete),
        application_id,
    )
    for model_id_to_delete in models_to_delete:
        delete_response = api_client.delete(
            f"/api/v1/symbolic/applications/{application_id}/models/{model_id_to_delete}"
        )
        if delete_response.status_code == 200:
            logger.info(
                "Deleted integration model application_id=%s model_id=%s",
                application_id,
                model_id_to_delete,
            )
        else:
            logger.error(
                "Failed deleting integration model application_id=%s model_id=%s status_code=%s body=%s",
                application_id,
                model_id_to_delete,
                delete_response.status_code,
                delete_response.text,
            )
        assert delete_response.status_code == 200
        delete_payload = delete_response.json()
        assert delete_payload["application_id"] == application_id
        assert delete_payload["model_id"] == model_id_to_delete
        assert delete_payload["deleted"] is True

    logger.info(
        "Deleted models summary for application_id=%s: \n   count=%s \n   ids=%s",
        application_id,
        len(models_to_delete),
        ", ".join(models_to_delete) if models_to_delete else "<none>",
    )
    return models_to_delete


def _insert_model(
    api_client: TestClient, application_id: str, model_data: dict[str, object]
) -> None:
    model_id = str(model_data["modelId"])
    post_response = api_client.post(
        f"/api/v1/symbolic/applications/{application_id}/models",
        json={
            **model_data,
            # Use a far-future timestamp so latest=true deterministically resolves to this model.
            "updatedAt": "2999-12-31T23:59:59Z",
            "createdAt": _now_iso(),
        },
    )
    if post_response.status_code == 200:
        logger.info(
            "Model insert succeeded for application_id=%s model_id=%s",
            application_id,
            model_id,
        )
    else:
        logger.error(
            "Model insert failed for application_id=%s model_id=%s status_code=%s body=%s",
            application_id,
            model_id,
            post_response.status_code,
            post_response.text,
        )

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["written"] == 1
    assert post_payload["symbolic_model"]["modelId"] == model_id
    assert post_payload["symbolic_model"]["isActive"] is bool(model_data["isActive"])


def _insert_variable(
    api_client: TestClient,
    application_id: str,
    model_id: str,
    variable_data: dict[str, object],
) -> None:
    variable_id = str(variable_data["variableId"])
    post_response = api_client.post(
        f"/api/v1/symbolic/applications/{application_id}/variables",
        json={
            "modelId": model_id,
            "variables": [
                {
                    **variable_data,
                }
            ],
            "dependencies": [],
        },
    )

    if post_response.status_code == 200:
        logger.info(
            "Variable insert succeeded for application_id=%s model_id=%s variable_id=%s",
            application_id,
            model_id,
            variable_id,
        )
    else:
        logger.error(
            "Variable insert failed for application_id=%s model_id=%s variable_id=%s status_code=%s body=%s",
            application_id,
            model_id,
            variable_id,
            post_response.status_code,
            post_response.text,
        )

    assert post_response.status_code == 200
    post_payload = post_response.json()
    assert post_payload["written"] >= 1
    assert any(
        variable["variableId"] == variable_id for variable in post_payload["variables"]
    )


def _create_session_execution_context(neo4j_db, application_id: str) -> tuple[str, str]:
    """Create a minimal session graph so symbolic session-values endpoints can be tested."""
    session_id = f"session-symbolic-test-{uuid4().hex[:12]}"
    state_id = f"state-symbolic-test-{uuid4().hex[:12]}"
    transition_id = f"transition-symbolic-test-{uuid4().hex[:12]}"
    execution_id = f"execution-symbolic-test-{uuid4().hex[:12]}"
    span_id = f"span-symbolic-test-{uuid4().hex[:12]}"

    neo4j_db.execute_command(
        """
		MATCH (mas:MAS {masName: $application_id})
		MERGE (session:Session {sessionId: $session_id})
		ON CREATE SET session.createdAt = $created_at
		SET session.updatedAt = $updated_at
		MERGE (session)-[:executesSession]->(mas)
		MERGE (state:State {stateId: $state_id})
		SET state.sessionId = $session_id
		MERGE (session)-[:hasState]->(state)
		MERGE (transition:Transition {transitionId: $transition_id})
		SET transition.sessionId = $session_id,
			transition.hierarchyLevel = 0
		MERGE (state)-[:inputTo]->(transition)
		MERGE (execution:ExecutionElement:LLMCall {executionId: $execution_id})
		SET execution.spanId = $span_id,
			execution.llmName = "symbolic-integration-test"
		MERGE (transition)-[:representsExecution]->(execution)
		""",
        {
            "application_id": application_id,
            "session_id": session_id,
            "state_id": state_id,
            "transition_id": transition_id,
            "execution_id": execution_id,
            "span_id": span_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    )

    return session_id, span_id


@pytest.fixture(scope="module")
def neo4j_db():
    """Return a live Neo4j connector or skip when integration infra is unavailable."""
    try:
        db = next(get_neo4j_db())
    except Exception as exc:  # pragma: no cover - depends on local infra
        pytest.skip(f"FAILED: Neo4j is not available for integration test: {exc}")

    if not db.is_connected():
        pytest.skip("FAILED: Neo4j connector is not connected for integration test")

    return db


@pytest.fixture()
def api_client(neo4j_db):
    """Use the live Neo4j connector through the API dependency override."""
    app.dependency_overrides[get_neo4j_db] = lambda: neo4j_db
    reset_client()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_neo4j_db, None)
        reset_client()


# @pytest.fixture(scope="module")
# def symbolic_context(neo4j_db):

# 	app_rows = neo4j_db.execute(
# 		"""
# 		MATCH (mas:MAS)
# 		RETURN mas.masName AS application_id
# 		ORDER BY application_id
# 		LIMIT 10
# 		""",
# 		{},
# 	)
# 	application_ids = [row["application_id"] for row in app_rows if row.get("application_id")]
# 	logger.debug(">>>")
# 	if application_ids:
# 		logger.info("app_rows:\n   %s", "\n   ".join(application_ids))
# 	else:
# 		logger.error(">>> app_rows: ERROR no results found")

# 	app_with_vars_rows = neo4j_db.execute(
# 		"""
# 		MATCH (mas:MAS)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
# 		WHERE coalesce(sm.isActive, false) = true
# 		MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
# 		RETURN
# 			mas.masName AS application_id,
# 			sm.modelId AS model_id,
# 			count(sv) AS variable_count
# 		ORDER BY variable_count DESC, application_id ASC
# 		LIMIT 10
# 		""",
# 		{},
# 	)
# 	app_with_vars_lines = [
# 		f"application_id={row.get('application_id')}, model_id={row.get('model_id')}, variable_count={row.get('variable_count')}"
# 		for row in app_with_vars_rows
# 	]
# 	if app_with_vars_lines:
# 		logger.info("app_with_vars_rows:\n   %s", "\n   ".join(app_with_vars_lines))
# 	else:
# 		logger.error(">>> app_with_vars_rows: ERROR no results found")

# 	session_rows = neo4j_db.execute(
# 		"""
# 		MATCH (session:Session)-[:executesSession]->(mas:MAS)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
# 		WHERE coalesce(sm.isActive, false) = true
# 		MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
# 		MATCH (session)-[:hasState|hasInitialState|hasFinalState*0..2]->(:State)-[:inputTo]->(:Transition)-[:representsExecution]->(execution)
# 		WITH session, mas, sm, sv, coalesce(execution.spanId, execution.span_id) AS span_id
# 		WHERE span_id IS NOT NULL AND sv.variableId IS NOT NULL
# 		RETURN
# 			session.sessionId AS session_id,
# 			mas.masName AS application_id,
# 			sm.modelId AS model_id,
# 			sv.variableId AS variable_id,
# 			span_id
# 		LIMIT 10
# 		""",
# 		{},
# 	)
# 	session_lines = [
# 		f"session_id={row.get('session_id')}, application_id={row.get('application_id')}, model_id={row.get('model_id')}, variable_id={row.get('variable_id')}, span_id={row.get('span_id')}"
# 		for row in session_rows
# 	]
# 	if session_lines:
# 		logger.info("session_rows:\n   %s", "\n   ".join(session_lines))
# 	else:
# 		logger.error(">>> session_rows: ERROR no results found")

# 	return {
# 		"application_for_models": test_application_id,
# 		"symbolic_test_application_id": test_application_id,
# 		"app_with_variables": app_with_vars_rows[0] if app_with_vars_rows else None,
# 		"session_context": session_rows[0] if session_rows else None,
# 	}

# application_id = symbolic_context["application_for_models"]
# if application_id is None:
# 	pytest.skip("No MAS nodes found in Neo4j to test symbolic model endpoints")


def test_application_models(api_client: TestClient, neo4j_db) -> None:
    """Discover real graph entities required by symbolic integration tests."""
    test_application_id = "mas-symbolic-TEST"
    neo4j_db.execute_command(
        """
		MERGE (mas:MAS {masName: $application_id})
		ON CREATE SET mas.createdAt = $created_at
		SET mas.updatedAt = $updated_at
		""",
        {
            "application_id": test_application_id,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        },
    )
    logger.info(
        "Created dedicated symbolic integration application_id=%s",
        test_application_id,
    )

    models_to_insert = [
        {
            "modelId": "sm_01",
            "version": "V1",
            "isActive": True,
            "modelName": "model1",
            "taskDescription": "Integration test model upsert",
        },
        {
            "modelId": "sm_02",
            "version": "V22",
            "isActive": False,
            "modelName": "model2",
            "taskDescription": "Integration test model upsert",
        },
        {
            "modelId": "sm_03",
            "version": "V3",
            "isActive": True,
            "modelName": "model3",
            "taskDescription": "Integration test model upsert",
        },
    ]

    for model_data in models_to_insert:
        _insert_model(api_client, test_application_id, model_data)

    variables_to_insert = [
        {
            "variableId": "sv-01",
            "name": "sv-01",
            "tier": "alignment",
            "type": "boolean",
            "description": "Integration test variable upsert",
            "extractionQuestion": "Was this variable inserted during integration test?",
            "discriminativeScore": 0.42,
            "isEnabledForEvaluation": True,
            "status": "active",
        },
        {
            "variableId": "sv-02",
            "name": "sv-02",
            "tier": "alignment",
            "type": "boolean",
            "description": "Integration test variable upsert",
            "extractionQuestion": "Was this variable inserted during integration test?",
            "discriminativeScore": 0.35,
            "isEnabledForEvaluation": True,
            "status": "active",
        },
        {
            "variableId": "sv-03",
            "name": "sv-03",
            "tier": "entity",
            "type": "boolean",
            "description": "Integration test variable upsert",
            "extractionQuestion": "Was this variable inserted during integration test?",
            "discriminativeScore": 0.27,
            "isEnabledForEvaluation": False,
            "status": "active",
        },
        {
            "variableId": "sv-04",
            "name": "sv-04",
            "tier": "process",
            "type": "boolean",
            "description": "Integration test variable upsert",
            "extractionQuestion": "Was this variable inserted during integration test?",
            "discriminativeScore": 0.62,
            "isEnabledForEvaluation": True,
            "status": "active",
        },
    ]

    model_id = str(models_to_insert[1]["modelId"])
    for variable_data in variables_to_insert:
        _insert_variable(api_client, test_application_id, model_id, variable_data)

    variables_to_insert_sm03 = [
        {
            "variableId": "sv-05",
            "name": "sv-05",
            "tier": "alignment",
            "type": "boolean",
            "description": "Integration test variable upsert",
            "extractionQuestion": "Was this variable inserted during integration test?",
            "discriminativeScore": 0.51,
            "isEnabledForEvaluation": True,
            "status": "active",
        },
        {
            "variableId": "sv-06",
            "name": "sv-06",
            "tier": "entity",
            "type": "boolean",
            "description": "Integration test variable upsert",
            "extractionQuestion": "Was this variable inserted during integration test?",
            "discriminativeScore": 0.18,
            "isEnabledForEvaluation": False,
            "status": "active",
        },
    ]

    model_id = str(models_to_insert[-1]["modelId"])
    for variable_data in variables_to_insert_sm03:
        _insert_variable(api_client, test_application_id, model_id, variable_data)

    # variable_id = str(variables_to_insert[0]["variableId"])

    ######

    get_all_response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/models"
    )

    assert get_all_response.status_code == 200
    get_all_payload = get_all_response.json()
    assert get_all_payload["application_id"] == test_application_id
    assert get_all_payload["count"] >= 1
    assert any(model["modelId"] == model_id for model in get_all_payload["models"])
    logger.debug(">>> get_all_response:")
    logger.debug(
        "models:\n%s",
        pformat(get_all_payload["models"], sort_dicts=False, width=100),
    )

    get_active_response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/models?activeOnly=true"
    )

    assert get_active_response.status_code == 200
    get_active_payload = get_active_response.json()
    assert get_active_payload["application_id"] == test_application_id
    assert get_active_payload["count"] >= 1
    assert any(model["modelId"] == model_id for model in get_active_payload["models"])
    logger.debug(">>> get_active_response:")
    logger.debug(
        "models:\n%s",
        pformat(get_active_payload["models"], sort_dicts=False, width=100),
    )

    get_latest_response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/models?latest=true"
    )

    assert get_latest_response.status_code == 200
    latest_payload = get_latest_response.json()
    assert latest_payload["count"] == 1
    assert latest_payload["models"][0]["modelId"] == model_id
    logger.debug(">>> get_latest_response:")
    logger.debug(
        "models:\n%s",
        pformat(latest_payload["models"], sort_dicts=False, width=100),
    )

    get_active_and_latest_response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/models?activeOnly=true&latest=true"
    )

    assert get_active_and_latest_response.status_code == 200
    active_and_latest_payload = get_active_and_latest_response.json()
    assert active_and_latest_payload["count"] == 1
    assert active_and_latest_payload["models"][0]["modelId"] == model_id
    logger.debug(">>> get_active_and_latest_response:")
    logger.debug(
        "models:\n%s",
        pformat(active_and_latest_payload["models"], sort_dicts=False, width=100),
    )

    model_id = "sm_02"
    get_by_id_response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/models/{model_id}"
    )

    assert get_by_id_response.status_code == 200
    by_id_payload = get_by_id_response.json()
    assert by_id_payload["application_id"] == test_application_id
    assert by_id_payload["symbolic_model"]["modelId"] == model_id
    logger.debug(">>> get_by_id_response:")
    logger.debug(
        "model:\n%s",
        pformat(by_id_payload["symbolic_model"], sort_dicts=False, width=100),
    )

    ######

    model_id = "sm_02"
    response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/variables?modelId={model_id}"
    )

    assert response.status_code == 200
    payload = response.json()
    logger.info("get_application_variables response:")
    logger.info(
        "payload:\n%s",
        pformat(payload, sort_dicts=False, width=100),
    )

    assert payload["application_id"] == test_application_id
    assert payload["count"] >= 1
    assert payload["variables"]
    # assert any(variable["variableId"] == variable_id for variable in payload["variables"])

    response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/variables"
    )

    assert response.status_code == 200
    payload = response.json()
    logger.info("get_application_variables response:")
    logger.info(
        "payload:\n%s",
        pformat(payload, sort_dicts=False, width=100),
    )

    assert payload["application_id"] == test_application_id
    assert payload["count"] >= 1
    assert payload["variables"]
    # assert any(variable["variableId"] == variable_id for variable in payload["variables"])

    ######

    session_id, span_id = _create_session_execution_context(
        neo4j_db, test_application_id
    )
    value_id = f"sval-integration-{uuid4().hex[:12]}"
    model_id = "sm_02"
    variable_id = "sv-01"

    post_session_values_response = api_client.post(
        f"/api/v1/symbolic/sessions/{session_id}/values",
        json={
            "modelId": model_id,
            "values": [
                {
                    "valueId": value_id,
                    "variableId": variable_id,
                    "variableName": variable_id,
                    "tier": "alignment",
                    "type": "boolean",
                    "value": False,
                    "reason": "integration test write",
                    "trajectoryIndex": 7,
                    "assignmentStrategy": "single_span",
                    "spanId": span_id,
                }
            ],
        },
    )

    assert post_session_values_response.status_code == 200
    post_session_values_payload = post_session_values_response.json()
    assert post_session_values_payload["session_id"] == session_id
    assert post_session_values_payload["symbolic_model"]["modelId"] == model_id
    assert post_session_values_payload["written"] == 1
    assert len(post_session_values_payload["values"]) == 1
    assert post_session_values_payload["values"][0]["valueId"] == value_id
    assert post_session_values_payload["values"][0]["variableId"] == variable_id
    assert post_session_values_payload["values"][0]["execution"]["spanId"] == span_id

    get_session_values_response = api_client.get(
        f"/api/v1/symbolic/sessions/{session_id}/values?modelId={model_id}"
    )
    assert get_session_values_response.status_code == 200
    get_session_values_payload = get_session_values_response.json()
    logger.info("get_session_values response:")
    logger.info(
        "payload:\n%s",
        pformat(get_session_values_payload, sort_dicts=False, width=100),
    )
    assert get_session_values_payload["session_id"] == session_id
    assert get_session_values_payload["symbolic_model"]["modelId"] == model_id
    assert get_session_values_payload["count"] >= 1
    assert any(
        item["valueId"] == value_id for item in get_session_values_payload["values"]
    )

    get_session_values_filtered_response = api_client.get(
        f"/api/v1/symbolic/sessions/{session_id}/values?modelId={model_id}&variableId={variable_id}&limit=1&offset=0"
    )
    assert get_session_values_filtered_response.status_code == 200
    get_session_values_filtered_payload = get_session_values_filtered_response.json()
    logger.info("get_session_values_filtered response:")
    logger.info(
        "payload:\n%s",
        pformat(get_session_values_filtered_payload, sort_dicts=False, width=100),
    )
    assert get_session_values_filtered_payload["count"] == 1
    assert get_session_values_filtered_payload["values"][0]["valueId"] == value_id

    get_session_values_by_name_response = api_client.get(
        f"/api/v1/symbolic/sessions/{session_id}/values?modelId={model_id}&variableName={variable_id}"
    )
    assert get_session_values_by_name_response.status_code == 200
    get_session_values_by_name_payload = get_session_values_by_name_response.json()
    logger.info("get_session_values_by_name response:")
    logger.info(
        "payload:\n%s",
        pformat(get_session_values_by_name_payload, sort_dicts=False, width=100),
    )
    assert get_session_values_by_name_payload["count"] >= 1
    assert any(
        item["valueId"] == value_id
        for item in get_session_values_by_name_payload["values"]
    )

    ######


def test_cleanup_delete_test_models(api_client: TestClient, neo4j_db) -> None:
    """Cleanup integration models after tests in this module."""
    if not FLAG_DELETE_TEST_MODELS:
        logger.info(
            "FLAG_DELETE_TEST_MODELS disabled: skipping integration model cleanup"
        )
        return

    test_application_id = "mas-symbolic-TEST"
    test_session_prefix = "session-symbolic-test-"
    test_state_prefix = "state-symbolic-test-"
    test_transition_prefix = "transition-symbolic-test-"
    test_execution_prefix = "execution-symbolic-test-"
    test_value_prefix = "sval-integration-"

    neo4j_db.execute_command(
        """
		MATCH (value:SymbolicValue)
		WHERE value.valueId STARTS WITH $value_prefix
		DETACH DELETE value
		""",
        {"value_prefix": test_value_prefix},
    )

    neo4j_db.execute_command(
        """
		MATCH (execution)
		WHERE execution.executionId STARTS WITH $execution_prefix
		DETACH DELETE execution
		""",
        {"execution_prefix": test_execution_prefix},
    )

    neo4j_db.execute_command(
        """
		MATCH (transition:Transition)
		WHERE transition.transitionId STARTS WITH $transition_prefix
		DETACH DELETE transition
		""",
        {"transition_prefix": test_transition_prefix},
    )

    neo4j_db.execute_command(
        """
		MATCH (state:State)
		WHERE state.stateId STARTS WITH $state_prefix
		DETACH DELETE state
		""",
        {"state_prefix": test_state_prefix},
    )

    neo4j_db.execute_command(
        """
		MATCH (session:Session)
		WHERE session.sessionId STARTS WITH $session_prefix
		DETACH DELETE session
		""",
        {"session_prefix": test_session_prefix},
    )

    get_models_response = api_client.get(
        f"/api/v1/symbolic/applications/{test_application_id}/models"
    )
    if get_models_response.status_code == 200:
        payload = get_models_response.json()
        for model in payload.get("models", []):
            model_id = model.get("modelId")
            if not isinstance(model_id, str) or not model_id:
                continue
            delete_response = api_client.delete(
                f"/api/v1/symbolic/applications/{test_application_id}/models/{model_id}"
            )
            assert delete_response.status_code == 200
    else:
        logger.info(
            "No models found for cleanup under application_id=%s (status=%s)",
            test_application_id,
            get_models_response.status_code,
        )

    neo4j_db.execute_command(
        """
		MATCH (mas:MAS {masName: $application_id})
		DETACH DELETE mas
		""",
        {"application_id": test_application_id},
    )

    verification_rows = neo4j_db.execute(
        """
		OPTIONAL MATCH (mas:MAS {masName: $application_id})
		OPTIONAL MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
		OPTIONAL MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
		OPTIONAL MATCH (session:Session)
			WHERE session.sessionId STARTS WITH $session_prefix
		OPTIONAL MATCH (state:State)
			WHERE state.stateId STARTS WITH $state_prefix
		OPTIONAL MATCH (transition:Transition)
			WHERE transition.transitionId STARTS WITH $transition_prefix
		OPTIONAL MATCH (execution)
			WHERE execution.executionId STARTS WITH $execution_prefix
		OPTIONAL MATCH (value:SymbolicValue)
			WHERE value.valueId STARTS WITH $value_prefix
		RETURN
			count(DISTINCT mas) AS mas_count,
			count(DISTINCT sm) AS model_count,
			count(DISTINCT sv) AS variable_count,
			count(DISTINCT session) AS session_count,
			count(DISTINCT state) AS state_count,
			count(DISTINCT transition) AS transition_count,
			count(DISTINCT execution) AS execution_count,
			count(DISTINCT value) AS symbolic_value_count
		""",
        {
            "application_id": test_application_id,
            "session_prefix": test_session_prefix,
            "state_prefix": test_state_prefix,
            "transition_prefix": test_transition_prefix,
            "execution_prefix": test_execution_prefix,
            "value_prefix": test_value_prefix,
        },
    )
    assert verification_rows
    assert verification_rows[0]["mas_count"] == 0
    assert verification_rows[0]["model_count"] == 0
    assert verification_rows[0]["variable_count"] == 0
    assert verification_rows[0]["session_count"] == 0
    assert verification_rows[0]["state_count"] == 0
    assert verification_rows[0]["transition_count"] == 0
    assert verification_rows[0]["execution_count"] == 0
    assert verification_rows[0]["symbolic_value_count"] == 0


### TEST SESSIONS

# session_rows = neo4j_db.execute(
# 	"""
# 	MATCH (session:Session)-[:executesSession]->(mas:MAS)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
# 	WHERE coalesce(sm.isActive, false) = true
# 	MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
# 	MATCH (session)-[:hasState|hasInitialState|hasFinalState*0..2]->(:State)-[:inputTo]->(:Transition)-[:representsExecution]->(execution)
# 	WITH session, mas, sm, sv, coalesce(execution.spanId, execution.span_id) AS span_id
# 	WHERE span_id IS NOT NULL AND sv.variableId IS NOT NULL
# 	RETURN
# 		session.sessionId AS session_id,
# 		mas.masName AS application_id,
# 		sm.modelId AS model_id,
# 		sv.variableId AS variable_id,
# 		span_id
# 	LIMIT 10
# 	""",
# 	{},
# )
# row = session_rows[0]
# session_id = row["session_id"]
# response = api_client.get(f"/api/v1/symbolic/sessions/{session_id}/state")

# assert response.status_code == 200
# state_payload = response.json()
# logger.info("get_session_state response:")
# logger.info(
# 	"state_payload:\n%s",
# 	pformat(state_payload, sort_dicts=False, width=100),
# )

# typed_response = SymbolicSessionStateResponse.model_validate(state_payload)
# assert isinstance(typed_response, SymbolicSessionStateResponse)
# assert typed_response.session_id == session_id
# assert typed_response.symbolic_model.modelId


# def test_session_values(api_client: TestClient, symbolic_context) -> None:
# 	row = symbolic_context["session_context"]
# 	if row is None:
# 		pytest.skip("No session context found with active model, variable, and execution span")

# 	session_id = row["session_id"]
# 	model_id = row["model_id"]
# 	variable_id = row["variable_id"]
# 	span_id = row["span_id"]
# 	value_id = f"sval_integration_{uuid4().hex[:12]}"

# 	post_response = api_client.post(
# 		f"/api/v1/symbolic/sessions/{session_id}/values",
# 		json={
# 			"modelId": model_id,
# 			"values": [
# 				{
# 					"valueId": value_id,
# 					"variableId": variable_id,
# 					"tier": "alignment",
# 					"type": "boolean",
# 					"value": False,
# 					"reason": "integration test write",
# 					"trajectoryIndex": 99999,
# 					"assignmentStrategy": "single_span",
# 					"spanId": span_id,
# 				}
# 			],
# 		},
# 	)
# 	get_values_response = api_client.get(f"/api/v1/symbolic/sessions/{session_id}/values")

# 	assert post_response.status_code == 200
# 	post_payload = post_response.json()
# 	assert post_payload["written"] >= 1
# 	assert any(item["valueId"] == value_id for item in post_payload["values"])

# 	assert get_values_response.status_code == 200
# 	payload = get_values_response.json()
# 	logger.debug("test_session_values response:")
# 	logger.debug(
# 		"payload:\n%s",
# 		pformat(payload, sort_dicts=False, width=100),
# 	)

# 	assert payload["session_id"] == session_id
# 	assert payload["count"] >= 1
# 	assert any(value["valueId"] == value_id for value in payload["values"])
