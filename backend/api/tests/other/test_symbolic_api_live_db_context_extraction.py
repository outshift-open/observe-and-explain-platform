#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pprint import pformat
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from oxp.api import app
from oxp.api.api_v1.endpoints.helpers import reset_client
from oxp.dependencies import get_neo4j_db

logger = logging.getLogger(__name__)

# FLAG_DELETE_TEST_MODELS = os.getenv("FLAG_DELETE_TEST_MODELS", "false").strip().lower() in {"1", "true", "yes", "y"}
FLAG_DELETE_TEST_MODELS = False


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


@pytest.fixture(scope="module")
def symbolic_context(neo4j_db):
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

    app_rows = neo4j_db.execute(
        """
		MATCH (mas:MAS)
		RETURN mas.masName AS application_id
		ORDER BY application_id
		LIMIT 10
		""",
        {},
    )
    application_ids = [
        row["application_id"] for row in app_rows if row.get("application_id")
    ]
    logger.debug(">>>")
    if application_ids:
        logger.info("app_rows:\n   %s", "\n   ".join(application_ids))
    else:
        logger.error(">>> app_rows: ERROR no results found")

    app_with_vars_rows = neo4j_db.execute(
        """
		MATCH (mas:MAS)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
		WHERE coalesce(sm.isActive, false) = true
		MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
		RETURN
			mas.masName AS application_id,
			sm.modelId AS model_id,
			count(sv) AS variable_count
		ORDER BY variable_count DESC, application_id ASC
		LIMIT 10
		""",
        {},
    )
    app_with_vars_lines = [
        f"application_id={row.get('application_id')}, model_id={row.get('model_id')}, variable_count={row.get('variable_count')}"
        for row in app_with_vars_rows
    ]
    if app_with_vars_lines:
        logger.info("app_with_vars_rows:\n   %s", "\n   ".join(app_with_vars_lines))
    else:
        logger.error(">>> app_with_vars_rows: ERROR no results found")

    session_rows = neo4j_db.execute(
        """
		MATCH (session:Session)-[:executesSession]->(mas:MAS)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
		WHERE coalesce(sm.isActive, false) = true
		MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
		MATCH (session)-[:hasState|hasInitialState|hasFinalState*0..2]->(:State)-[:inputTo]->(:Transition)-[:representsExecution]->(execution)
		WITH session, mas, sm, sv, coalesce(execution.spanId, execution.span_id) AS span_id
		WHERE span_id IS NOT NULL AND sv.variableId IS NOT NULL
		RETURN
			session.sessionId AS session_id,
			mas.masName AS application_id,
			sm.modelId AS model_id,
			sv.variableId AS variable_id,
			span_id
		LIMIT 10
		""",
        {},
    )
    session_lines = [
        f"session_id={row.get('session_id')}, application_id={row.get('application_id')}, model_id={row.get('model_id')}, variable_id={row.get('variable_id')}, span_id={row.get('span_id')}"
        for row in session_rows
    ]
    if session_lines:
        logger.info("session_rows:\n   %s", "\n   ".join(session_lines))
    else:
        logger.error(">>> session_rows: ERROR no results found")

    return {
        "application_for_models": test_application_id,
        "symbolic_test_application_id": test_application_id,
        "app_with_variables": app_with_vars_rows[0] if app_with_vars_rows else None,
        "session_context": session_rows[0] if session_rows else None,
    }


def test_application_models(api_client: TestClient, symbolic_context) -> None:
    application_id = symbolic_context["application_for_models"]
    if application_id is None:
        pytest.skip("No MAS nodes found in Neo4j to test symbolic model endpoints")

    model_id = f"sm_integration_{uuid4().hex[:12]}"
    post_response = api_client.post(
        f"/api/v1/symbolic/applications/{application_id}/models",
        json={
            "modelId": model_id,
            "version": "integration",
            "isActive": True,
            "modelName": "integration-test",
            "taskDescription": "Integration test model upsert",
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
    assert post_payload["symbolic_model"]["isActive"] is True
    symbolic_context["inserted_application_model"] = {
        "application_id": application_id,
        "model_id": model_id,
    }

    get_all_response = api_client.get(
        f"/api/v1/symbolic/applications/{application_id}/models"
    )

    assert get_all_response.status_code == 200
    get_all_payload = get_all_response.json()
    assert get_all_payload["application_id"] == application_id
    assert get_all_payload["count"] >= 1
    assert any(model["modelId"] == model_id for model in get_all_payload["models"])
    logger.debug(">>> get_all_response:")
    logger.debug(
        "models:\n%s",
        pformat(get_all_payload["models"], sort_dicts=False, width=100),
    )

    get_active_response = api_client.get(
        f"/api/v1/symbolic/applications/{application_id}/models?activeOnly=true"
    )

    assert get_active_response.status_code == 200
    get_active_payload = get_active_response.json()
    assert get_active_payload["application_id"] == application_id
    assert get_active_payload["count"] >= 1
    assert any(model["modelId"] == model_id for model in get_active_payload["models"])
    logger.debug(">>> get_active_response:")
    logger.debug(
        "models:\n%s",
        pformat(get_active_payload["models"], sort_dicts=False, width=100),
    )

    get_latest_response = api_client.get(
        f"/api/v1/symbolic/applications/{application_id}/models?latest=true"
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
        f"/api/v1/symbolic/applications/{application_id}/models?activeOnly=true&latest=true"
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

    get_by_id_response = api_client.get(
        f"/api/v1/symbolic/applications/{application_id}/models/{model_id}"
    )

    assert get_by_id_response.status_code == 200
    by_id_payload = get_by_id_response.json()
    assert by_id_payload["application_id"] == application_id
    assert by_id_payload["symbolic_model"]["modelId"] == model_id
    logger.debug(">>> get_by_id_response:")
    logger.debug(
        "model:\n%s",
        pformat(by_id_payload["symbolic_model"], sort_dicts=False, width=100),
    )


# def test_application_variables(api_client: TestClient, symbolic_context) -> None:
# 	row = symbolic_context.get("inserted_application_model")
# 	if row is None:
# 		row = symbolic_context["app_with_variables"]
# 	if row is None:
# 		pytest.skip("No symbolic model context found to insert variables")

# 	application_id = row["application_id"]
# 	model_id = row["model_id"]
# 	variable_id = f"sv_integration_{uuid4().hex[:12]}"

# 	post_response = api_client.post(
# 		f"/api/v1/symbolic/applications/{application_id}/variables",
# 		json={
# 			"modelId": model_id,
# 			"variables": [
# 				{
# 					"variableId": variable_id,
# 					"name": variable_id,
# 					"tier": "alignment",
# 					"type": "boolean",
# 					"description": "Integration test variable upsert",
# 					"extractionQuestion": "Was this variable inserted during integration test?",
# 					"discriminativeScore": 0.42,
# 					"isEnabledForEvaluation": True,
# 					"status": "active",
# 				}
# 			],
# 			"dependencies": [],
# 		},
# 	)

# 	if post_response.status_code == 200:
# 		logger.info(
# 			"Variable insert succeeded for application_id=%s model_id=%s variable_id=%s",
# 			application_id,
# 			model_id,
# 			variable_id,
# 		)
# 	else:
# 		logger.error(
# 			"Variable insert failed for application_id=%s model_id=%s variable_id=%s status_code=%s body=%s",
# 			application_id,
# 			model_id,
# 			variable_id,
# 			post_response.status_code,
# 			post_response.text,
# 		)

# 	assert post_response.status_code == 200
# 	post_payload = post_response.json()
# 	assert post_payload["written"] >= 1
# 	assert any(variable["variableId"] == variable_id for variable in post_payload["variables"])

# 	response = api_client.get(f"/api/v1/symbolic/applications/{application_id}/variables")

# 	assert response.status_code == 200
# 	payload = response.json()
# 	logger.debug("get_application_variables response:")
# 	logger.debug(
# 		"payload:\n%s",
# 		pformat(payload, sort_dicts=False, width=100),
# 	)

# 	assert payload["application_id"] == application_id
# 	assert payload["count"] >= 1
# 	assert payload["variables"]
# 	assert any(variable["variableId"] == variable_id for variable in payload["variables"])


def test_cleanup_delete_test_models(api_client: TestClient, symbolic_context) -> None:
    """Cleanup integration models after tests in this module."""
    if not FLAG_DELETE_TEST_MODELS:
        logger.info(
            "FLAG_DELETE_TEST_MODELS disabled: skipping integration model cleanup"
        )
        return

    row = symbolic_context.get("inserted_application_model")
    if row is None:
        logger.info(
            "No inserted application model found in symbolic_context: skipping cleanup"
        )
        return

    _delete_integration_models_for_application(api_client, row["application_id"])


# def test_get_session_state(api_client: TestClient, symbolic_context) -> None:
# 	row = symbolic_context["session_context"]
# 	if row is None:
# 		pytest.skip("No session context found with active model, variable, and execution span")

# 	session_id = row["session_id"]
# 	response = api_client.get(f"/api/v1/symbolic/sessions/{session_id}/state")

# 	assert response.status_code == 200
# 	state_payload = response.json()
# 	logger.debug("get_session_state response:")
# 	logger.debug(
# 		"state_payload:\n%s",
# 		pformat(state_payload, sort_dicts=False, width=100),
# 	)

# 	typed_response = SymbolicSessionStateResponse.model_validate(state_payload)
# 	assert isinstance(typed_response, SymbolicSessionStateResponse)
# 	assert typed_response.session_id == session_id
# 	assert typed_response.symbolic_model.modelId


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
