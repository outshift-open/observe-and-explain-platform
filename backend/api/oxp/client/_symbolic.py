#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Symbolic-domain methods for :class:`LocalClient`."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import logging
import re
from typing import Any

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError, NotFoundError, ValidationError
from oxp.models.otel_traces import (
    SymbolicModelDeleteResponse,
    SymbolicModelResponse,
    SymbolicModelSummary,
    SymbolicModelsResponse,
    SymbolicModelWriteResponse,
    SymbolicSessionStateResponse,
    SymbolicSessionValuesResponse,
    SymbolicSessionValuesWriteResponse,
    SymbolicStateExecutionReference,
    SymbolicStateItem,
    SymbolicValueExecutionReference,
    SymbolicValueItem,
    SymbolicVariableItem,
    SymbolicVariablesResponse,
    SymbolicVariablesWriteResponse,
)
from oxp.query_builders import symbolic as symbolic_queries

logger = logging.getLogger(__name__)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slugify_variable_id(name: str) -> str:
    normalized = _NON_ALNUM_RE.sub("_", name.strip().lower()).strip("_")
    return normalized or "symbolic_variable"


class SymbolicClient:
    """Symbolic operations mixed into :class:`LocalClient`."""

    db: Connector

    def _fetch_one(
        self, query: str, params: dict[str, Any], *, ctx: str
    ) -> dict[str, Any] | None:
        try:
            rows = self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to execute symbolic query for {ctx}: {exc}"
            ) from exc
        return rows[0] if rows else None

    def _fetch_all(
        self, query: str, params: dict[str, Any], *, ctx: str
    ) -> list[dict[str, Any]]:
        try:
            return self.db.execute(query, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to execute symbolic query for {ctx}: {exc}"
            ) from exc

    def _execute(self, command: str, params: dict[str, Any], *, ctx: str) -> None:
        try:
            self.db.execute_command(command, params)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to execute symbolic command for {ctx}: {exc}"
            ) from exc

    def _model_summary_from_row(self, row: dict[str, Any]) -> SymbolicModelSummary:
        return SymbolicModelSummary(
            modelId=row.get("modelId", ""),
            version=row.get("version"),
            createdAt=row.get("createdAt") or row.get("modelCreatedAt"),
            updatedAt=row.get("updatedAt") or row.get("modelUpdatedAt"),
            isActive=bool(row.get("isActive", False)),
            modelName=row.get("modelName"),
            taskDescription=row.get("taskDescription"),
        )

    def _value_execution_ref_from_row(
        self, row: dict[str, Any]
    ) -> SymbolicValueExecutionReference | None:
        span_id = row.get("spanId")
        if not span_id:
            return None
        execution_labels = row.get("executionLabels")
        if execution_labels is None:
            execution_labels = [
                label
                for flag, label in (
                    (row.get("isToolCall"), "ToolCall"),
                    (row.get("isLLMCall"), "LLMCall"),
                    (row.get("isProcessingCall"), "ProcessingCall"),
                    (row.get("isExecutionElement"), "ExecutionElement"),
                )
                if flag
            ]
        entity_type = row.get("entityType")
        if entity_type is None and execution_labels:
            entity_type = next(
                (label for label in execution_labels if label != "ExecutionElement"),
                execution_labels[0],
            )
        return SymbolicValueExecutionReference(
            executionId=row.get("executionId"),
            spanId=span_id,
            entityType=entity_type,
            entityName=row.get("entityName"),
        )

    def _state_execution_ref_from_row(
        self, row: dict[str, Any]
    ) -> SymbolicStateExecutionReference | None:
        span_id = row.get("spanId")
        if not span_id:
            return None
        execution_labels = row.get("executionLabels")
        if execution_labels is None:
            execution_labels = [
                label
                for flag, label in (
                    (row.get("isToolCall"), "ToolCall"),
                    (row.get("isLLMCall"), "LLMCall"),
                    (row.get("isProcessingCall"), "ProcessingCall"),
                    (row.get("isExecutionElement"), "ExecutionElement"),
                )
                if flag
            ]
        return SymbolicStateExecutionReference(
            executionId=row.get("executionId"),
            spanId=span_id,
            entityName=row.get("entityName"),
            executionLabels=execution_labels or [],
        )

    def _variable_item_from_row(self, row: dict[str, Any]) -> SymbolicVariableItem:
        return SymbolicVariableItem(
            variableId=row.get("variableId"),
            name=row.get("name", ""),
            tier=row.get("tier", "entity"),
            type=row.get("type", ""),
            description=row.get("description") or "",
            extractionQuestion=row.get("extractionQuestion"),
            discriminativeScore=row.get("discriminativeScore"),
            isEnabledForEvaluation=row.get("isEnabledForEvaluation"),
            foundationMetric=row.get("foundationMetric"),
            status=row.get("status"),
            createdAt=row.get("createdAt"),
            updatedAt=row.get("updatedAt"),
            dependsOn=[dep for dep in (row.get("dependsOn") or []) if dep],
        )

    def _require_application_model(
        self, application_id: str, model_id: str | None = None
    ) -> SymbolicModelSummary:
        query, params = (
            symbolic_queries.symbolic_model_by_application_query(
                application_id, model_id
            )
            if model_id is not None
            else symbolic_queries.active_symbolic_model_by_application_query(
                application_id
            )
        )
        row = self._fetch_one(query, params, ctx=f"application '{application_id}'")
        if row is None:
            raise NotFoundError(
                f"No symbolic model found for application '{application_id}'."
            )
        return self._model_summary_from_row(row)

    def _require_session_model(
        self, session_id: str, model_id: str | None = None
    ) -> SymbolicModelSummary:
        query, params = (
            symbolic_queries.symbolic_model_by_session_query(session_id, model_id)
            if model_id is not None
            else symbolic_queries.active_symbolic_model_by_session_query(session_id)
        )
        row = self._fetch_one(query, params, ctx=f"session '{session_id}'")
        if row is None:
            raise NotFoundError(f"No symbolic model found for session '{session_id}'.")
        return self._model_summary_from_row(row)

    def get_application_symbolic_models(
        self,
        application_id: str,
        *,
        active_only: bool = False,
        latest: bool = False,
    ) -> SymbolicModelsResponse:
        """Return symbolic models for an application."""
        query, params = symbolic_queries.symbolic_models_by_application_query(
            application_id,
            active_only=active_only,
            latest=latest,
        )
        rows = self._fetch_all(
            query, params, ctx=f"application '{application_id}' models"
        )
        if not rows:
            raise NotFoundError(
                f"No symbolic model found for application '{application_id}'."
            )

        models = [
            self._model_summary_from_row(row) for row in rows if row.get("modelId")
        ]
        if not models:
            raise NotFoundError(
                f"No symbolic model found for application '{application_id}'."
            )

        return SymbolicModelsResponse(
            application_id=application_id,
            count=len(models),
            models=models,
        )

    def get_application_symbolic_model(
        self,
        application_id: str,
        model_id: str,
    ) -> SymbolicModelResponse:
        """Return one symbolic model by application and model id."""
        symbolic_model = self._require_application_model(application_id, model_id)
        return SymbolicModelResponse(
            application_id=application_id,
            symbolic_model=symbolic_model,
        )

    def delete_application_symbolic_model(
        self,
        application_id: str,
        model_id: str,
    ) -> SymbolicModelDeleteResponse:
        """Delete one symbolic model by application and model id."""
        self._require_application_model(application_id, model_id)
        command, params = symbolic_queries.delete_symbolic_model_query(
            application_id, model_id
        )
        self._execute(
            command, params, ctx=f"application '{application_id}' model '{model_id}'"
        )
        return SymbolicModelDeleteResponse(
            application_id=application_id,
            model_id=model_id,
            deleted=True,
        )

    def write_application_symbolic_model(
        self,
        application_id: str,
        *,
        model_id: str,
        version: str | None,
        is_active: bool,
        model_name: str | None,
        task_description: str | None,
        updated_at: str | None,
        created_at: str | None,
    ) -> SymbolicModelWriteResponse:
        """Create or update a symbolic model for an application."""
        timestamp = updated_at or _now_iso()
        command, params = symbolic_queries.upsert_symbolic_model_query(
            application_id,
            model_id,
            version=version,
            is_active=is_active,
            model_name=model_name,
            task_description=task_description,
            updated_at=timestamp,
            created_at=created_at,
        )
        self._execute(
            command, params, ctx=f"application '{application_id}' model '{model_id}'"
        )
        symbolic_model = self._require_application_model(application_id, model_id)
        return SymbolicModelWriteResponse(
            application_id=application_id,
            written=1,
            symbolic_model=symbolic_model,
            errors=[],
        )

    def get_application_symbolic_variables(
        self,
        application_id: str,
        *,
        model_id: str | None = None,
        evaluation_only: bool = False,
    ) -> SymbolicVariablesResponse:
        """Return symbolic variables for one application model."""
        symbolic_model = self._require_application_model(application_id, model_id)
        query, params = symbolic_queries.application_symbolic_variables_query(
            application_id,
            symbolic_model.modelId,
            evaluation_only=evaluation_only,
        )
        rows = self._fetch_all(
            query, params, ctx=f"application '{application_id}' variables"
        )
        variables = [
            self._variable_item_from_row(row) for row in rows if row.get("variableId")
        ]
        return SymbolicVariablesResponse(
            application_id=application_id,
            symbolic_model=symbolic_model,
            count=len(variables),
            variables=variables,
        )

    def write_application_symbolic_variables(
        self,
        application_id: str,
        *,
        model_id: str,
        variables: list[dict[str, Any]],
        dependencies: list[dict[str, Any]],
        min_discriminative_score: float | None = None,
    ) -> SymbolicVariablesWriteResponse:
        """Upsert symbolic variables and their dependencies for an application."""
        symbolic_model = self._require_application_model(application_id, model_id)

        prepared_variables: list[dict[str, Any]] = []
        seen_variable_ids: set[str] = set()
        for variable in variables:
            variable_id = variable.get("variableId") or _slugify_variable_id(
                variable["name"]
            )
            if variable_id in seen_variable_ids:
                raise ValidationError(
                    f"Duplicate symbolic variableId '{variable_id}' in request."
                )
            seen_variable_ids.add(variable_id)
            prepared = dict(variable)
            prepared["variableId"] = variable_id
            prepared_variables.append(prepared)

        errors: list[str] = []
        written = 0
        timestamp = _now_iso()

        dependency_groups: dict[str, list[str]] = {
            item["variableId"]: [] for item in prepared_variables
        }
        for dep in dependencies:
            dependency_groups.setdefault(dep["variableId"], []).append(
                dep["dependsOnVariableId"]
            )

        successful_variable_ids: set[str] = set()

        for variable in prepared_variables:
            variable_id = variable["variableId"]
            is_enabled_for_evaluation = variable.get("isEnabledForEvaluation")
            if (
                is_enabled_for_evaluation is None
                and min_discriminative_score is not None
            ):
                score = variable.get("discriminativeScore")
                if score is not None:
                    is_enabled_for_evaluation = float(score) >= min_discriminative_score

            command, params = symbolic_queries.upsert_symbolic_variable_query(
                application_id,
                model_id,
                variable_id=variable_id,
                name=variable["name"],
                tier=variable["tier"],
                value_type=variable["type"],
                description=variable.get("description") or "",
                extraction_question=variable.get("extractionQuestion"),
                discriminative_score=variable.get("discriminativeScore"),
                is_enabled_for_evaluation=is_enabled_for_evaluation,
                foundation_metric=variable.get("foundationMetric"),
                status=variable.get("status"),
                created_at=variable.get("createdAt"),
                updated_at=variable.get("updatedAt") or timestamp,
            )
            try:
                self._execute(command, params, ctx=f"variable '{variable_id}'")
                written += 1
                successful_variable_ids.add(variable_id)
            except (DatabaseError, ValidationError) as exc:
                errors.append(str(exc))

        for variable_id in successful_variable_ids:
            try:
                clear_command, clear_params = (
                    symbolic_queries.clear_symbolic_variable_dependencies_query(
                        application_id,
                        model_id,
                        variable_id,
                    )
                )
                self._execute(
                    clear_command,
                    clear_params,
                    ctx=f"clear dependencies for '{variable_id}'",
                )
                for depends_on_variable_id in dependency_groups.get(variable_id, []):
                    dep_query, dep_params = (
                        symbolic_queries.symbolic_variable_exists_query(
                            application_id,
                            model_id,
                            depends_on_variable_id,
                        )
                    )
                    if (
                        self._fetch_one(
                            dep_query,
                            dep_params,
                            ctx=f"dependency '{depends_on_variable_id}'",
                        )
                        is None
                    ):
                        raise ValidationError(
                            f"Dependency target '{depends_on_variable_id}' does not exist in symbolic model '{model_id}'."
                        )
                    link_command, link_params = (
                        symbolic_queries.create_symbolic_variable_dependency_query(
                            application_id,
                            model_id,
                            variable_id,
                            depends_on_variable_id,
                        )
                    )
                    self._execute(
                        link_command,
                        link_params,
                        ctx=f"dependency '{variable_id}' -> '{depends_on_variable_id}'",
                    )
            except (DatabaseError, ValidationError) as exc:
                errors.append(str(exc))

        persisted = self.get_application_symbolic_variables(
            application_id,
            model_id=model_id,
        )
        return SymbolicVariablesWriteResponse(
            application_id=application_id,
            symbolic_model=symbolic_model,
            written=written,
            count=persisted.count,
            variables=persisted.variables,
            errors=errors,
        )

    def write_session_symbolic_values(
        self,
        session_id: str,
        *,
        model_id: str,
        values: list[dict[str, Any]],
    ) -> SymbolicSessionValuesWriteResponse:
        """Append symbolic value events to a session."""
        session_query, session_params = symbolic_queries.session_exists_query(
            session_id
        )
        if (
            self._fetch_one(
                session_query, session_params, ctx=f"session '{session_id}' existence"
            )
            is None
        ):
            raise NotFoundError(f"Session '{session_id}' was not found.")

        symbolic_model = self._require_session_model(session_id, model_id)
        written = 0
        errors: list[str] = []
        persisted_values: list[SymbolicValueItem] = []
        timestamp = _now_iso()

        for value in values:
            try:
                var_query, var_params = (
                    symbolic_queries.symbolic_variable_for_session_query(
                        session_id,
                        model_id,
                        value["variableId"],
                    )
                )
                if (
                    self._fetch_one(
                        var_query,
                        var_params,
                        ctx=f"symbolic variable '{value['variableId']}'",
                    )
                    is None
                ):
                    raise ValidationError(
                        f"Symbolic variable '{value['variableId']}' does not exist in model '{model_id}'."
                    )

                exec_query, exec_params = (
                    symbolic_queries.session_execution_by_span_query(
                        session_id,
                        value["spanId"],
                    )
                )
                execution_row = self._fetch_one(
                    exec_query, exec_params, ctx=f"span '{value['spanId']}'"
                )
                if execution_row is None:
                    raise ValidationError(
                        f"Span '{value['spanId']}' does not resolve to a session-local execution element."
                    )

                command, params = symbolic_queries.append_symbolic_value_query(
                    session_id,
                    model_id,
                    value_id=value["valueId"],
                    variable_id=value["variableId"],
                    tier=value["tier"],
                    value_type=value["type"],
                    value=value.get("value"),
                    reason=value.get("reason"),
                    trajectory_index=value["trajectoryIndex"],
                    assignment_strategy=value.get("assignmentStrategy"),
                    created_at=value.get("createdAt") or timestamp,
                    span_id=value["spanId"],
                )
                self._execute(
                    command, params, ctx=f"symbolic value '{value['valueId']}'"
                )
                persisted_values.append(
                    SymbolicValueItem(
                        valueId=value["valueId"],
                        variableId=value["variableId"],
                        variableName=value.get("variableName"),
                        tier=value["tier"],
                        type=value["type"],
                        value=value.get("value"),
                        reason=value.get("reason"),
                        trajectoryIndex=value["trajectoryIndex"],
                        assignmentStrategy=value.get("assignmentStrategy"),
                        createdAt=value.get("createdAt") or timestamp,
                        execution=self._value_execution_ref_from_row(execution_row),
                    )
                )
                written += 1
            except (DatabaseError, ValidationError) as exc:
                errors.append(str(exc))

        return SymbolicSessionValuesWriteResponse(
            session_id=session_id,
            symbolic_model=symbolic_model,
            written=written,
            errors=errors,
            values=persisted_values,
        )

    def get_session_symbolic_values(
        self,
        session_id: str,
        *,
        model_id: str | None = None,
        variable_id: str | None = None,
        variable_name: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> SymbolicSessionValuesResponse:
        """Return symbolic value events for a session."""
        symbolic_model = self._require_session_model(session_id, model_id)
        query, params = symbolic_queries.session_symbolic_values_query(
            session_id,
            symbolic_model.modelId,
            variable_id=variable_id,
            variable_name=variable_name,
            limit=limit,
            offset=offset,
        )
        rows = self._fetch_all(query, params, ctx=f"session '{session_id}' values")
        values = [
            SymbolicValueItem(
                valueId=row["valueId"],
                variableId=row["variableId"],
                variableName=row.get("variableName"),
                tier=row.get("tier", "entity"),
                type=row.get("type", ""),
                value=row.get("value"),
                reason=row.get("reason"),
                trajectoryIndex=row.get("trajectoryIndex", 0),
                assignmentStrategy=row.get("assignmentStrategy"),
                createdAt=row.get("createdAt"),
                execution=self._value_execution_ref_from_row(row),
            )
            for row in rows
            if row.get("valueId") and row.get("variableId")
        ]

        return SymbolicSessionValuesResponse(
            session_id=session_id,
            symbolic_model=symbolic_model,
            count=len(values),
            values=values,
        )

    def get_session_symbolic_state(
        self, session_id: str
    ) -> SymbolicSessionStateResponse:
        """Return the final symbolic state for a session."""
        query, params = symbolic_queries.session_symbolic_state_query(session_id)
        rows = self._fetch_all(query, params, ctx=f"session '{session_id}' state")
        if not rows:
            raise NotFoundError(f"No symbolic model found for session '{session_id}'.")

        symbolic_model = self._model_summary_from_row(rows[0])
        state = [
            SymbolicStateItem(
                valueId=row["valueId"],
                variableId=row["variableId"],
                tier=row.get("tier", "entity"),
                type=row.get("type", ""),
                value=row.get("value"),
                reason=row.get("reason"),
                trajectoryIndex=row.get("trajectoryIndex", 0),
                assignmentStrategy=row.get("assignmentStrategy"),
                createdAt=row.get("createdAt"),
                execution=self._state_execution_ref_from_row(row),
            )
            for row in rows
            if row.get("valueId") and row.get("variableId")
        ]
        return SymbolicSessionStateResponse(
            session_id=session_id,
            symbolic_model=symbolic_model,
            count=len(state),
            state=state,
        )

    def get_sessions_count(
        self,
        *,
        application_id: str,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> dict[str, int]:
        """Return the count of sessions linked to an application."""
        params: dict[str, Any] = {"application_id": application_id}
        conditions: list[str] = []
        if start_time is not None:
            conditions.append("s.startTime >= $start_time")
            params["start_time"] = start_time
        if end_time is not None:
            conditions.append("s.startTime <= $end_time")
            params["end_time"] = end_time

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = (
            "MATCH (s:Session)-[]-(ma:MAS) WHERE ma.id = $application_id "
            "WITH DISTINCT s "
            f"{where_clause} "
            "RETURN count(s) AS count"
        )
        rows = self._fetch_all(
            query,
            params,
            ctx=f"session count for application '{application_id}'",
        )
        count_value = rows[0].get("count") if rows else 0
        return {"count": int(count_value or 0)}

    def get_session_reasoning_path(self, *, session_id: str) -> dict[str, Any]:
        """Return a symbolic reasoning graph for a single session."""
        graph_query = (
            "MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS) "
            "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel) "
            "WHERE coalesce(sm.isActive, false) = true "
            "MATCH (sm)-[:DEFINES_VARIABLE]->(var:SymbolicVariable) "
            "OPTIONAL MATCH (var)-[:DEPENDS_ON]->(dep:SymbolicVariable) "
            "WITH sm, session, var, collect(DISTINCT dep.variableId) AS dependsOn "
            "WITH sm, session, collect({var: var, dependsOn: dependsOn}) AS allVars "
            "WITH sm, session, allVars, "
            "  reduce(s = [], v IN allVars | "
            "    CASE WHEN coalesce(v.var.isEnabledForEvaluation, false) = true "
            "    THEN s + v.dependsOn ELSE s END"
            "  ) AS enabledDeps "
            "UNWIND allVars AS entry "
            "WITH sm, session, entry.var AS var, entry.dependsOn AS dependsOn, enabledDeps "
            "WHERE coalesce(var.isEnabledForEvaluation, false) = true "
            "  OR var.variableId IN enabledDeps "
            "RETURN "
            "  sm.modelId AS modelId, "
            "  sm.version AS modelVersion, "
            "  sm.modelName AS modelName, "
            "  var.variableId AS variableId, "
            "  var.name AS name, "
            "  var.tier AS tier, "
            "  var.type AS type, "
            "  var.description AS description, "
            "  coalesce(var.isEnabledForEvaluation, false) AS isEnabledForEvaluation, "
            "  coalesce( "
            "    properties(var)['discriminativeScore'], "
            "    properties(var)['discriminationScore'], "
            "    properties(var)['discriminatingScore'] "
            "  ) AS discriminativeScore, "
            "  dependsOn "
            "ORDER BY coalesce(var.tier, ''), coalesce(var.name, '')"
        )
        graph_records = self._fetch_all(
            graph_query,
            {"session_id": session_id},
            ctx=f"reasoning graph for session '{session_id}'",
        )

        history_query = (
            "MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS) "
            "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel) "
            "WHERE coalesce(sm.isActive, false) = true "
            "MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(val:SymbolicValue)"
            "-[:INSTANCE_OF]->(var:SymbolicVariable)<-[:DEFINES_VARIABLE]-(sm) "
            "OPTIONAL MATCH (val)-[:ABOUT_EXECUTION]->(exec) "
            "RETURN "
            "  var.variableId AS variableId, "
            "  val.valueId AS valueId, "
            "  val.value AS value, "
            "  val.reason AS reason, "
            "  val.trajectoryIndex AS trajectoryIndex, "
            "  val.assignmentStrategy AS assignmentStrategy, "
            "  exec.spanId AS spanId, "
            "  exec.executionId AS executionId, "
            "  COALESCE( "
            "    exec.agentName, exec.llmName, exec.modelName, "
            "    exec.toolName, exec.processingName, "
            "    CASE "
            "      WHEN exec.entityName IS NOT NULL "
            "        AND exec.entityName <> 'unknown' "
            "      THEN exec.entityName ELSE null "
            "    END, "
            "    exec.executionType "
            "  ) AS entityName, "
            "  labels(exec) AS executionLabels, "
            "  exec.timestamp AS executionTimestamp, "
            "  exec.duration AS executionDuration, "
            "  exec.toolName AS toolName, "
            "  exec.processingName AS processingName, "
            "  exec.llmName AS llmName, "
            "  exec.modelName AS modelName, "
            "  exec.inputParams AS inputParams, "
            "  exec.outputContent AS outputContent, "
            "  exec.toolOutput AS toolOutput, "
            "  exec.promptTokenCount AS promptTokenCount, "
            "  exec.completionTokenCount AS completionTokenCount, "
            "  exec.totalTokenCount AS totalTokenCount "
            "ORDER BY val.trajectoryIndex ASC, coalesce(val.createdAt, '') ASC"
        )
        history_records = self._fetch_all(
            history_query,
            {"session_id": session_id},
            ctx=f"reasoning history for session '{session_id}'",
        )

        score_query = (
            "MATCH (s:Session {sessionId: $session_id})-[:hasMetric]->(m:Metric) "
            "WHERE m.metricName = 'trajectory_score' "
            "  AND m.source = 'SymbolicDiscovery' "
            "RETURN m.value AS value, m.source AS source "
            "LIMIT 1"
        )
        score_records = self._fetch_all(
            score_query,
            {"session_id": session_id},
            ctx=f"reasoning score for session '{session_id}'",
        )

        if not graph_records:
            return {
                "sessionId": session_id,
                "model": None,
                "trajectoryScore": None,
                "evaluationRounds": [],
                "nodes": [],
                "edges": [],
            }

        first = graph_records[0]
        model_info = {
            "modelId": first["modelId"],
            "version": first["modelVersion"],
            "modelName": first["modelName"],
        }

        trajectory_score = score_records[0]["value"] if score_records else None

        history_by_variable: dict[str, list[dict[str, Any]]] = {}
        all_indices: set[int] = set()
        seen_value_ids: set[str] = set()
        for rec in history_records:
            value_id = rec.get("valueId")
            if value_id in seen_value_ids:
                continue
            seen_value_ids.add(value_id)

            var_id = rec.get("variableId")
            idx = rec.get("trajectoryIndex")
            if isinstance(idx, int):
                all_indices.add(idx)

            entry = {
                "valueId": value_id,
                "value": rec.get("value"),
                "reason": rec.get("reason"),
                "trajectoryIndex": idx,
                "assignmentStrategy": rec.get("assignmentStrategy"),
                "spanId": rec.get("spanId"),
                "executionId": rec.get("executionId"),
                "entityName": rec.get("entityName"),
                "executionLabels": rec.get("executionLabels"),
                "executionTimestamp": rec.get("executionTimestamp"),
                "executionDuration": rec.get("executionDuration"),
                "toolName": rec.get("toolName"),
                "processingName": rec.get("processingName"),
                "llmName": rec.get("llmName"),
                "modelName": rec.get("modelName"),
                "inputParams": rec.get("inputParams"),
                "outputContent": rec.get("outputContent"),
                "toolOutput": rec.get("toolOutput"),
                "promptTokenCount": rec.get("promptTokenCount"),
                "completionTokenCount": rec.get("completionTokenCount"),
                "totalTokenCount": rec.get("totalTokenCount"),
            }
            history_by_variable.setdefault(str(var_id), []).append(entry)

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for record in graph_records:
            variable_id = record.get("variableId")
            history = history_by_variable.get(str(variable_id), [])
            latest = history[-1] if history else None
            nodes.append(
                {
                    "id": variable_id,
                    "name": record.get("name"),
                    "tier": record.get("tier"),
                    "type": record.get("type"),
                    "description": record.get("description"),
                    "isEnabledForEvaluation": record.get("isEnabledForEvaluation"),
                    "discriminativeScore": record.get("discriminativeScore"),
                    "value": latest["value"] if latest else None,
                    "reason": latest["reason"] if latest else None,
                    "trajectoryIndex": latest["trajectoryIndex"] if latest else None,
                    "assignmentStrategy": latest["assignmentStrategy"]
                    if latest
                    else None,
                    "valueId": latest["valueId"] if latest else None,
                    "spanId": latest["spanId"] if latest else None,
                    "executionId": latest["executionId"] if latest else None,
                    "entityName": latest["entityName"] if latest else None,
                    "executionLabels": latest["executionLabels"] if latest else None,
                    "toolName": latest["toolName"] if latest else None,
                    "processingName": latest["processingName"] if latest else None,
                    "llmName": latest["llmName"] if latest else None,
                    "modelName": latest["modelName"] if latest else None,
                    "executionTimestamp": latest["executionTimestamp"]
                    if latest
                    else None,
                    "executionDuration": latest["executionDuration"]
                    if latest
                    else None,
                    "inputParams": latest["inputParams"] if latest else None,
                    "outputContent": latest["outputContent"] if latest else None,
                    "toolOutput": latest["toolOutput"] if latest else None,
                    "promptTokenCount": latest["promptTokenCount"] if latest else None,
                    "completionTokenCount": latest["completionTokenCount"]
                    if latest
                    else None,
                    "totalTokenCount": latest["totalTokenCount"] if latest else None,
                    "history": history,
                }
            )
            for dep_id in record.get("dependsOn") or []:
                edges.append(
                    {
                        "source": variable_id,
                        "target": dep_id,
                        "relationship": "DEPENDS_ON",
                    }
                )

        return {
            "sessionId": session_id,
            "model": model_info,
            "trajectoryScore": trajectory_score,
            "evaluationRounds": sorted(all_indices),
            "nodes": nodes,
            "edges": edges,
        }

    def get_timeline_reasoning_path(self, *, session_id: str) -> dict[str, Any]:
        """Return symbolic value assignments grouped by execution span."""
        enabled_query = (
            "MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS) "
            "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel) "
            "WHERE coalesce(sm.isActive, false) = true "
            "MATCH (sm)-[:DEFINES_VARIABLE]->(var:SymbolicVariable) "
            "OPTIONAL MATCH (var)-[:DEPENDS_ON]->(dep:SymbolicVariable) "
            "WITH var, collect(DISTINCT dep.variableId) AS deps "
            "WITH collect({var: var, deps: deps}) AS allVars "
            "WITH allVars, "
            "  reduce(s = [], v IN allVars | "
            "    CASE WHEN coalesce(v.var.isEnabledForEvaluation, false) = true "
            "    THEN s + v.deps ELSE s END"
            "  ) AS enabledDeps "
            "UNWIND allVars AS entry "
            "WITH entry.var AS var, entry.deps AS deps, enabledDeps "
            "WHERE coalesce(var.isEnabledForEvaluation, false) = true "
            "  OR var.variableId IN enabledDeps "
            "RETURN var.variableId AS variableId, var.tier AS tier, deps AS dependsOn"
        )
        enabled_rows = self._fetch_all(
            enabled_query,
            {"session_id": session_id},
            ctx=f"timeline reasoning variable filter for session '{session_id}'",
        )

        valid_var_ids: list[str] = []
        dep_map: dict[str, list[str]] = {}
        tier_map: dict[str, str] = {}
        for row in enabled_rows:
            vid = str(row.get("variableId") or "")
            if not vid:
                continue
            valid_var_ids.append(vid)
            tier_map[vid] = str(row.get("tier") or "")
            dep_map[vid] = [d for d in (row.get("dependsOn") or []) if d]

        query = (
            "MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS) "
            "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel) "
            "WHERE coalesce(sm.isActive, false) = true "
            "MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(val:SymbolicValue)"
            "-[:INSTANCE_OF]->(var:SymbolicVariable)<-[:DEFINES_VARIABLE]-(sm) "
            "WHERE var.variableId IN $valid_var_ids "
            "MATCH (val)-[:ABOUT_EXECUTION]->(exec) "
            "RETURN "
            "  exec.spanId AS spanId, "
            "  exec.executionId AS executionId, "
            "  labels(exec) AS executionLabels, "
            "  COALESCE( "
            "    exec.agentName, exec.llmName, exec.modelName, "
            "    exec.toolName, exec.processingName, "
            "    CASE "
            "      WHEN exec.entityName IS NOT NULL "
            "        AND exec.entityName <> 'unknown' "
            "      THEN exec.entityName ELSE null "
            "    END, "
            "    exec.executionType "
            "  ) AS entityName, "
            "  exec.timestamp AS executionTimestamp, "
            "  exec.duration AS executionDuration, "
            "  var.variableId AS variableId, "
            "  var.name AS variableName, "
            "  var.tier AS tier, "
            "  val.valueId AS valueId, "
            "  val.value AS value, "
            "  val.reason AS reason, "
            "  val.trajectoryIndex AS trajectoryIndex, "
            "  val.assignmentStrategy AS assignmentStrategy "
            "ORDER BY exec.spanId, var.name, val.trajectoryIndex ASC"
        )
        records = self._fetch_all(
            query,
            {"session_id": session_id, "valid_var_ids": valid_var_ids},
            ctx=f"timeline reasoning records for session '{session_id}'",
        )

        spans: dict[str, dict[str, Any]] = {}
        seen_value_ids: set[str] = set()

        for rec in records:
            value_id = rec.get("valueId")
            if value_id in seen_value_ids:
                continue
            seen_value_ids.add(value_id)

            span_id = str(rec.get("spanId") or "")
            if span_id not in spans:
                spans[span_id] = {
                    "spanId": span_id,
                    "executionId": rec.get("executionId"),
                    "entityName": rec.get("entityName"),
                    "executionLabels": rec.get("executionLabels"),
                    "executionTimestamp": rec.get("executionTimestamp"),
                    "executionDuration": rec.get("executionDuration"),
                    "variables": {},
                }

            var_id = str(rec.get("variableId") or "")
            idx = rec.get("trajectoryIndex")
            existing = spans[span_id]["variables"].get(var_id)
            if existing is None or (
                idx is not None and (existing.get("trajectoryIndex") or -1) < idx
            ):
                spans[span_id]["variables"][var_id] = {
                    "variableId": var_id,
                    "name": rec.get("variableName"),
                    "tier": rec.get("tier"),
                    "value": rec.get("value"),
                    "reason": rec.get("reason"),
                    "trajectoryIndex": idx,
                    "assignmentStrategy": rec.get("assignmentStrategy"),
                    "executionId": rec.get("executionId"),
                    "entityName": rec.get("entityName"),
                    "executionLabels": rec.get("executionLabels"),
                }

        global_latest: dict[str, list[tuple[int, dict[str, Any]]]] = {}
        for span in spans.values():
            for var_entry in span["variables"].values():
                vid = str(var_entry.get("variableId") or "")
                idx = int(var_entry.get("trajectoryIndex") or 0)
                global_latest.setdefault(vid, []).append((idx, var_entry))
        for entries in global_latest.values():
            entries.sort(key=lambda item: item[0])

        def _latest_value_at(var_id: str, max_idx: int) -> dict[str, Any] | None:
            entries = global_latest.get(var_id, [])
            best = None
            for idx, entry in entries:
                if idx <= max_idx:
                    best = entry
                else:
                    break
            return best

        alignment_var_ids = {
            vid for vid, tier in tier_map.items() if tier == "alignment"
        }

        result: list[dict[str, Any]] = []
        for span in spans.values():
            all_vars = span["variables"]

            dep_var_ids: set[str] = set()
            for alignment_id in alignment_var_ids:
                if alignment_id in all_vars:
                    for dep_id in dep_map.get(alignment_id, []):
                        dep_var_ids.add(dep_id)

            nested: list[dict[str, Any]] = []
            for alignment_id in sorted(
                (var_id for var_id in all_vars if var_id in alignment_var_ids),
                key=lambda var_id: all_vars[var_id].get("name") or "",
            ):
                alignment_var = dict(all_vars[alignment_id])
                alignment_idx = int(alignment_var.get("trajectoryIndex") or 0)
                children = []
                for dep_id in dep_map.get(alignment_id, []):
                    dep_val = _latest_value_at(dep_id, alignment_idx)
                    if dep_val is not None:
                        children.append(dep_val)
                alignment_var["dependencies"] = sorted(
                    children,
                    key=lambda value: (
                        value.get("tier") or "",
                        value.get("name") or "",
                    ),
                )
                nested.append(alignment_var)

            top_level = [
                all_vars[var_id]
                for var_id in sorted(
                    all_vars,
                    key=lambda v: (
                        all_vars[v].get("tier") or "",
                        all_vars[v].get("name") or "",
                    ),
                )
                if var_id not in alignment_var_ids and var_id not in dep_var_ids
            ]

            span["variables"] = nested + top_level
            result.append(span)

        result.sort(key=lambda span: span.get("executionTimestamp") or 0)
        return {"sessionId": session_id, "spans": result}

    def get_application_reasoning_path(self, *, mas_name: str) -> dict[str, Any]:
        """Return an aggregated symbolic reasoning path across MAS sessions."""
        skeleton_query = (
            "MATCH (mas:MAS {id: $mas_name}) "
            "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel) "
            "WHERE coalesce(sm.isActive, false) = true "
            "MATCH (sm)-[:DEFINES_VARIABLE]->(var:SymbolicVariable) "
            "OPTIONAL MATCH (var)-[:DEPENDS_ON]->(dep:SymbolicVariable) "
            "WITH sm, var, collect(DISTINCT dep.variableId) AS dependsOn "
            "WITH sm, collect({var: var, dependsOn: dependsOn}) AS allVars "
            "WITH sm, allVars, "
            "  reduce(s = [], v IN allVars | "
            "    CASE WHEN coalesce(v.var.isEnabledForEvaluation, false) = true "
            "    THEN s + v.dependsOn ELSE s END"
            "  ) AS enabledDeps "
            "UNWIND allVars AS entry "
            "WITH sm, entry.var AS var, entry.dependsOn AS dependsOn, enabledDeps "
            "WHERE coalesce(var.isEnabledForEvaluation, false) = true "
            "  OR var.variableId IN enabledDeps "
            "RETURN "
            "  sm.modelId AS modelId, "
            "  sm.version AS modelVersion, "
            "  sm.modelName AS modelName, "
            "  var.variableId AS variableId, "
            "  var.name AS name, "
            "  var.tier AS tier, "
            "  var.type AS type, "
            "  var.description AS description, "
            "  coalesce(var.isEnabledForEvaluation, false) AS isEnabledForEvaluation, "
            "  coalesce( "
            "    properties(var)['discriminativeScore'], "
            "    properties(var)['discriminationScore'], "
            "    properties(var)['discriminatingScore'] "
            "  ) AS discriminativeScore, "
            "  dependsOn "
            "ORDER BY coalesce(var.tier, ''), coalesce(var.name, '')"
        )
        skeleton_records = self._fetch_all(
            skeleton_query,
            {"mas_name": mas_name},
            ctx=f"application reasoning skeleton for '{mas_name}'",
        )

        if not skeleton_records:
            return {
                "masName": mas_name,
                "model": None,
                "totalSessions": 0,
                "nodes": [],
                "edges": [],
            }

        variable_ids = [row.get("variableId") for row in skeleton_records]

        scores_query = (
            "MATCH (mas:MAS {id: $mas_name})<-[:executesSession]-(s:Session) "
            "MATCH (s)-[:hasMetric]->(m:Metric) "
            "WHERE m.metricName = 'trajectory_score' "
            "  AND m.source = 'SymbolicDiscovery' "
            "RETURN s.sessionId AS sessionId, m.value AS score"
        )
        scores_records = self._fetch_all(
            scores_query,
            {"mas_name": mas_name},
            ctx=f"application reasoning scores for '{mas_name}'",
        )
        score_by_session: dict[str, float] = {
            str(record.get("sessionId")): record.get("score")
            for record in scores_records
        }
        valid_session_ids = list(score_by_session.keys())

        agg_query = (
            "MATCH (mas:MAS {id: $mas_name}) "
            "MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel) "
            "WHERE coalesce(sm.isActive, false) = true "
            "MATCH (sm)-[:DEFINES_VARIABLE]->(var:SymbolicVariable) "
            "WHERE var.variableId IN $variable_ids "
            "OPTIONAL MATCH (val:SymbolicValue)-[:INSTANCE_OF]->(var) "
            "OPTIONAL MATCH (s:Session)-[:HAS_SYMBOLIC_VALUE]->(val) "
            "WHERE (s)-[:executesSession]->(mas) "
            "  AND s.sessionId IN $valid_session_ids "
            "WITH var, s, val "
            "ORDER BY val.trajectoryIndex ASC "
            "WITH var, s, "
            "  collect(val.trajectoryIndex)[-1] AS lastIdx, "
            "  collect(val.value)[-1] AS finalValue "
            "WITH var, "
            "  collect(CASE WHEN s IS NOT NULL AND finalValue IS NOT NULL THEN { "
            "    sessionId: s.sessionId, "
            "    value: finalValue, "
            "    lastTrajectoryIndex: lastIdx "
            "  } END) AS rawSessions, "
            "  avg(lastIdx) AS avgLastIndex "
            "WITH var, avgLastIndex, "
            "  [entry IN rawSessions WHERE entry IS NOT NULL] AS sessions "
            "RETURN "
            "  var.variableId AS variableId, "
            "  size(sessions) AS sessionCount, "
            "  avgLastIndex, "
            "  sessions "
        )
        agg_records = self._fetch_all(
            agg_query,
            {
                "mas_name": mas_name,
                "variable_ids": variable_ids,
                "valid_session_ids": valid_session_ids,
            },
            ctx=f"application reasoning aggregation for '{mas_name}'",
        )

        first = skeleton_records[0]
        model_info = {
            "modelId": first.get("modelId"),
            "version": first.get("modelVersion"),
            "modelName": first.get("modelName"),
        }

        total_sessions = len(score_by_session)
        passed_count = sum(1 for value in score_by_session.values() if value == 1)
        failed_count = sum(1 for value in score_by_session.values() if value == 0)

        agg_by_variable: dict[str, dict[str, Any]] = {}
        for record in agg_records:
            sessions = record.get("sessions") or []
            enriched: list[dict[str, Any]] = []
            for session in sessions:
                sid = session.get("sessionId")
                score = score_by_session.get(str(sid))
                enriched.append(
                    {
                        **session,
                        "trajectoryScore": score,
                        "passed": score == 1 if score is not None else None,
                    }
                )

            values = [s.get("value") for s in enriched if s.get("value") is not None]
            distribution: dict[str, int] = {}
            for value in values:
                key = str(value)
                distribution[key] = distribution.get(key, 0) + 1

            variable_id = str(record.get("variableId") or "")
            agg_by_variable[variable_id] = {
                "sessionCount": record.get("sessionCount"),
                "avgLastTrajectoryIndex": record.get("avgLastIndex"),
                "sessions": enriched,
                "distribution": distribution,
                "distinctValueCount": len(distribution),
            }

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for record in skeleton_records:
            variable_id = str(record.get("variableId") or "")
            agg = agg_by_variable.get(
                variable_id,
                {
                    "sessionCount": 0,
                    "avgLastTrajectoryIndex": None,
                    "sessions": [],
                    "distribution": {},
                    "distinctValueCount": 0,
                },
            )
            nodes.append(
                {
                    "id": variable_id,
                    "name": record.get("name"),
                    "tier": record.get("tier"),
                    "type": record.get("type"),
                    "description": record.get("description"),
                    "isEnabledForEvaluation": record.get("isEnabledForEvaluation"),
                    "discriminativeScore": record.get("discriminativeScore"),
                    "sessionCount": agg["sessionCount"],
                    "avgLastTrajectoryIndex": agg["avgLastTrajectoryIndex"],
                    "distribution": agg["distribution"],
                    "distinctValueCount": agg["distinctValueCount"],
                    "sessions": agg["sessions"],
                }
            )
            for dep_id in record.get("dependsOn") or []:
                edges.append(
                    {
                        "source": variable_id,
                        "target": dep_id,
                        "relationship": "DEPENDS_ON",
                    }
                )

        return {
            "masName": mas_name,
            "model": model_info,
            "totalSessions": total_sessions,
            "passedSessions": passed_count,
            "failedSessions": failed_count,
            "nodes": nodes,
            "edges": edges,
        }

    def get_applications_with_stateful_eval(
        self,
        *,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return fatal/minor stateful-eval totals per application."""
        time_filter = ""
        if start_time is not None:
            time_filter += "AND s.startTime >= $start_time "
        if end_time is not None:
            time_filter += "AND s.startTime <= $end_time "

        query = (
            "MATCH (s:Session)-[]-(ma:MAS) "
            f"WHERE true {time_filter}"
            "WITH DISTINCT s, ma "
            "MATCH (s)-[:hasMetric]->(m:Metric) "
            "WHERE m.metricName IN ['trajectory_score', 'statefulEval'] "
            "  AND m.reasoning IS NOT NULL "
            "RETURN ma.id AS applicationName, "
            "  collect(m.reasoning) AS reasonings"
        )
        rows = self._fetch_all(
            query,
            {"start_time": start_time, "end_time": end_time},
            ctx="applications with stateful eval",
        )

        applications: list[dict[str, Any]] = []
        for row in rows:
            fatal_sum = 0
            minor_sum = 0
            for raw_reasoning in row.get("reasonings") or []:
                if not raw_reasoning:
                    continue
                try:
                    reasoning = raw_reasoning
                    if isinstance(reasoning, str):
                        reasoning = json.loads(reasoning)
                    if isinstance(reasoning, str):
                        reasoning = json.loads(reasoning)
                    fatal_sum += int(reasoning.get("total_fatal", 0) or 0)
                    minor_sum += int(reasoning.get("total_minor", 0) or 0)
                except (ValueError, TypeError, AttributeError, json.JSONDecodeError):
                    continue

            applications.append(
                {
                    "applicationName": row.get("applicationName"),
                    "totalFatal": fatal_sum,
                    "totalMinor": minor_sum,
                }
            )

        return applications
