#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the symbolic neurosymbolic endpoint domain.

These builders target the MVP graph model described in the symbolic API PDF.
They keep Cypher localized so the client mixin can focus on mapping rows to
response models.
"""

from __future__ import annotations

from typing import Any


def active_symbolic_model_by_application_query(
    application_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return the active symbolic model for an application."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
    WHERE coalesce(sm.isActive, false) = true
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS createdAt,
        sm.updatedAt AS updatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription
    ORDER BY coalesce(sm.updatedAt, sm.createdAt, "") DESC
    LIMIT 1
    """
    return query, {"application_id": application_id}


def symbolic_model_by_application_query(
    application_id: str,
    model_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return a specific symbolic model attached to an application."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS createdAt,
        sm.updatedAt AS updatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription
    LIMIT 1
    """
    return query, {"application_id": application_id, "model_id": model_id}


def symbolic_models_by_application_query(
    application_id: str,
    *,
    active_only: bool = False,
    latest: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Return symbolic models attached to an application."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
    """
    if active_only:
        query += """
    WHERE coalesce(sm.isActive, false) = true
    """

    query += """
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS createdAt,
        sm.updatedAt AS updatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription
    ORDER BY coalesce(sm.updatedAt, "") DESC, coalesce(sm.createdAt, "") DESC, coalesce(sm.modelId, "") DESC
    """

    if latest:
        query += """
    LIMIT 1
    """

    return query, {"application_id": application_id}


def upsert_symbolic_model_query(
    application_id: str,
    model_id: str,
    *,
    version: str | None,
    is_active: bool,
    model_name: str | None,
    task_description: str | None,
    updated_at: str,
    created_at: str | None,
) -> tuple[str, dict[str, Any]]:
    """Create or update one symbolic model on an application."""
    query = """
    MATCH (mas:MAS {id: $application_id})
    MERGE (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    ON CREATE SET sm.createdAt = coalesce($created_at, $updated_at)
    SET
        sm.version = $version,
        sm.updatedAt = $updated_at,
        sm.isActive = $is_active,
        sm.modelName = $model_name,
        sm.taskDescription = $task_description
    WITH mas, sm
    OPTIONAL MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(other:SymbolicModel)
    WHERE $is_active = true AND other.modelId <> sm.modelId
    SET other.isActive = false
    RETURN sm.modelId AS modelId
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
        "version": version,
        "is_active": is_active,
        "model_name": model_name,
        "task_description": task_description,
        "updated_at": updated_at,
        "created_at": created_at,
    }


def delete_symbolic_model_query(
    application_id: str,
    model_id: str,
) -> tuple[str, dict[str, Any]]:
    """Delete a symbolic model and symbolic variables defined under it."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    OPTIONAL MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
    WITH sm, collect(DISTINCT sv) AS variables
    FOREACH (variable IN variables | DETACH DELETE variable)
    DETACH DELETE sm
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
    }


def active_symbolic_model_by_session_query(
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return the active symbolic model for the application that owns a session."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
    WHERE coalesce(sm.isActive, false) = true
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS createdAt,
        sm.updatedAt AS updatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription
    ORDER BY coalesce(sm.updatedAt, sm.createdAt, "") DESC
    LIMIT 1
    """
    return query, {"session_id": session_id}


def symbolic_model_by_session_query(
    session_id: str,
    model_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return a specific symbolic model attached to a session's MAS."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS createdAt,
        sm.updatedAt AS updatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription
    LIMIT 1
    """
    return query, {"session_id": session_id, "model_id": model_id}


def application_symbolic_variables_query(
    application_id: str,
    model_id: str,
    *,
    evaluation_only: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Return symbolic variables for one model on an application."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    OPTIONAL MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable)
    OPTIONAL MATCH (sv)-[:DEPENDS_ON]->(dep:SymbolicVariable)
    WITH sv, collect(DISTINCT coalesce(dep.variableId, dep.name)) AS dependsOn
    WHERE
        sv IS NOT NULL
        AND ($evaluation_only = false OR coalesce(sv.isEnabledForEvaluation, false) = true)
    RETURN
        sv.variableId AS variableId,
        sv.name AS name,
        sv.tier AS tier,
        sv.type AS type,
        sv.description AS description,
        sv.extractionQuestion AS extractionQuestion,
        coalesce(
            properties(sv)['discriminativeScore'],
            properties(sv)['discriminationScore'],
            properties(sv)['discriminatingScore']
        ) AS discriminativeScore,
        sv.isEnabledForEvaluation AS isEnabledForEvaluation,
        sv.foundationMetric AS foundationMetric,
        sv.status AS status,
        sv.createdAt AS createdAt,
        sv.updatedAt AS updatedAt,
        dependsOn AS dependsOn
    ORDER BY coalesce(sv.tier, ""), coalesce(sv.name, "")
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
        "evaluation_only": evaluation_only,
    }


def symbolic_variable_exists_query(
    application_id: str,
    model_id: str,
    variable_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return the variable if it already exists on the target model."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})
    RETURN sv.variableId AS variableId
    LIMIT 1
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
        "variable_id": variable_id,
    }


def upsert_symbolic_variable_query(
    application_id: str,
    model_id: str,
    *,
    variable_id: str,
    name: str,
    tier: str,
    value_type: str,
    description: str = "",
    extraction_question: str | None = None,
    discriminative_score: float | None = None,
    is_enabled_for_evaluation: bool | None = None,
    foundation_metric: str | None = None,
    status: str | None = None,
    created_at: str | None = None,
    updated_at: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create or update one symbolic variable on a symbolic model."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    MERGE (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})
    ON CREATE SET sv.createdAt = coalesce($created_at, $updated_at)
    SET
        sv.name = $name,
        sv.tier = $tier,
        sv.type = $value_type,
        sv.description = $description,
        sv.extractionQuestion = $extraction_question,
        sv.discriminativeScore = $discriminative_score,
        sv.isEnabledForEvaluation = $is_enabled_for_evaluation,
        sv.foundationMetric = $foundation_metric,
        sv.status = $status,
        sv.updatedAt = $updated_at
    RETURN sv.variableId AS variableId
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
        "variable_id": variable_id,
        "name": name,
        "tier": tier,
        "value_type": value_type,
        "description": description,
        "extraction_question": extraction_question,
        "discriminative_score": discriminative_score,
        "is_enabled_for_evaluation": is_enabled_for_evaluation,
        "foundation_metric": foundation_metric,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def clear_symbolic_variable_dependencies_query(
    application_id: str,
    model_id: str,
    variable_id: str,
) -> tuple[str, dict[str, Any]]:
    """Delete outgoing dependency edges for one symbolic variable."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})-[rel:DEPENDS_ON]->(:SymbolicVariable)
    DELETE rel
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
        "variable_id": variable_id,
    }


def create_symbolic_variable_dependency_query(
    application_id: str,
    model_id: str,
    variable_id: str,
    depends_on_variable_id: str,
) -> tuple[str, dict[str, Any]]:
    """Create one dependency edge between symbolic variables on a model."""
    query = """
    MATCH (mas:MAS {id: $application_id})-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})
    MATCH (sm)-[:DEFINES_VARIABLE]->(dep:SymbolicVariable {variableId: $depends_on_variable_id})
    MERGE (sv)-[:DEPENDS_ON]->(dep)
    RETURN dep.variableId AS variableId
    """
    return query, {
        "application_id": application_id,
        "model_id": model_id,
        "variable_id": variable_id,
        "depends_on_variable_id": depends_on_variable_id,
    }


def session_exists_query(session_id: str) -> tuple[str, dict[str, Any]]:
    """Check that a session exists."""
    query = """
    MATCH (session:Session {sessionId: $session_id})
    RETURN session.sessionId AS sessionId
    LIMIT 1
    """
    return query, {"session_id": session_id}


def symbolic_variable_for_session_query(
    session_id: str,
    model_id: str,
    variable_id: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve a symbolic variable for the model active on a session's MAS."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    MATCH (sm)-[:DEFINES_VARIABLE]->(sv:SymbolicVariable {variableId: $variable_id})
    RETURN sv.variableId AS variableId
    LIMIT 1
    """
    return query, {
        "session_id": session_id,
        "model_id": model_id,
        "variable_id": variable_id,
    }


def session_execution_by_span_query(
    session_id: str,
    span_id: str,
) -> tuple[str, dict[str, Any]]:
    """Resolve a session-local execution element by span identifier."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:hasState|hasInitialState|hasFinalState*0..2]->(:State)-[:inputTo]->(:Transition)-[:representsExecution]->(execution)
    WHERE coalesce(execution.spanId, execution.span_id) = $span_id
    RETURN
        coalesce(execution.executionId, execution.id) AS executionId,
        coalesce(execution.spanId, execution.span_id) AS spanId,
        COALESCE(
            execution.agentName,
            execution.agent_name,
            execution.llmName,
            execution.llm_name,
            execution.modelName,
            execution.toolName,
            execution.tool_name,
            execution.masName,
            execution["mas_name"],
            execution["taskName"],
            execution["task_name"],
            execution.processingName,
            execution.processing_name,
            CASE
                WHEN execution.entityName IS NOT NULL AND execution.entityName <> 'unknown'
                THEN execution.entityName
                ELSE null
            END,
            execution.executionType
        ) AS entityName,
        labels(execution) AS executionLabels
    LIMIT 1
    """
    return query, {"session_id": session_id, "span_id": span_id}


def append_symbolic_value_query(
    session_id: str,
    model_id: str,
    *,
    value_id: str,
    variable_id: str,
    tier: str,
    value_type: str,
    value: Any,
    reason: str | None = None,
    trajectory_index: int,
    assignment_strategy: str | None = None,
    created_at: str | None = None,
    span_id: str,
) -> tuple[str, dict[str, Any]]:
    """Append one symbolic value event to a session."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    MATCH (sm)-[:DEFINES_VARIABLE]->(var:SymbolicVariable {variableId: $variable_id})
    MATCH (session)-[:hasState|hasInitialState|hasFinalState*0..2]->(:State)-[:inputTo]->(:Transition)-[:representsExecution]->(execution)
    WHERE coalesce(execution.spanId, execution.span_id) = $span_id
    MERGE (session)-[:HAS_SYMBOLIC_VALUE]->(symbolicValue:SymbolicValue {valueId: $value_id})
    ON CREATE SET symbolicValue.createdAt = $created_at
    SET
        symbolicValue.variableId = $variable_id,
        symbolicValue.tier = $tier,
        symbolicValue.type = $value_type,
        symbolicValue.value = $value,
        symbolicValue.reason = $reason,
        symbolicValue.trajectoryIndex = $trajectory_index,
        symbolicValue.assignmentStrategy = $assignment_strategy
    MERGE (symbolicValue)-[:INSTANCE_OF]->(var)
    MERGE (symbolicValue)-[:ABOUT_EXECUTION]->(execution)
    RETURN symbolicValue.valueId AS valueId
    """
    return query, {
        "session_id": session_id,
        "model_id": model_id,
        "value_id": value_id,
        "variable_id": variable_id,
        "tier": tier,
        "value_type": value_type,
        "value": value,
        "reason": reason,
        "trajectory_index": trajectory_index,
        "assignment_strategy": assignment_strategy,
        "created_at": created_at,
        "span_id": span_id,
    }


def session_symbolic_state_query(
    session_id: str,
) -> tuple[str, dict[str, Any]]:
    """Return the final symbolic state for a session."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel)
    WHERE coalesce(sm.isActive, false) = true
    OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(value:SymbolicValue)-[:INSTANCE_OF]->(var:SymbolicVariable)<-[:DEFINES_VARIABLE]-(sm)
    OPTIONAL MATCH (value)-[:ABOUT_EXECUTION]->(execution)
    WITH sm, var, value, execution
    ORDER BY coalesce(value.trajectoryIndex, -1) DESC, coalesce(value.createdAt, "") DESC, coalesce(value.valueId, "") DESC
    WITH sm, var, collect({value: value, execution: execution})[0] AS latest
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS modelCreatedAt,
        sm.updatedAt AS modelUpdatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription,
        var.name AS name,
        latest.value.valueId AS valueId,
        latest.value.variableId AS variableId,
        latest.value.tier AS tier,
        latest.value.type AS type,
        latest.value.value AS value,
        latest.value.reason AS reason,
        latest.value.trajectoryIndex AS trajectoryIndex,
        latest.value.assignmentStrategy AS assignmentStrategy,
        latest.value.createdAt AS createdAt,
        coalesce(latest.execution.executionId, latest.execution.id) AS executionId,
        coalesce(latest.execution.spanId, latest.execution.span_id) AS spanId,
        COALESCE(
            latest.execution.agentName,
            latest.execution.agent_name,
            latest.execution.llmName,
            latest.execution.llm_name,
            latest.execution.modelName,
            latest.execution.toolName,
            latest.execution.tool_name,
            latest.execution.masName,
            latest.execution["mas_name"],
            latest.execution["taskName"],
            latest.execution["task_name"],
            latest.execution.processingName,
            latest.execution.processing_name,
            CASE
                WHEN latest.execution.entityName IS NOT NULL AND latest.execution.entityName <> 'unknown'
                THEN latest.execution.entityName
                ELSE null
            END,
            latest.execution.executionType
        ) AS entityName,
        latest.execution:ToolCall IS NOT NULL AS isToolCall,
        latest.execution:LLMCall IS NOT NULL AS isLLMCall,
        latest.execution:ProcessingCall IS NOT NULL AS isProcessingCall,
        latest.execution:ExecutionElement IS NOT NULL AS isExecutionElement
    ORDER BY coalesce(var.tier, ""), coalesce(var.name, "")
    """
    return query, {"session_id": session_id}


def session_symbolic_values_query(
    session_id: str,
    model_id: str,
    *,
    variable_id: str | None = None,
    variable_name: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Return symbolic value events for a session and selected symbolic model."""
    query = """
    MATCH (session:Session {sessionId: $session_id})-[:executesSession]->(mas:MAS)
    MATCH (mas)-[:HAS_SYMBOLIC_MODEL]->(sm:SymbolicModel {modelId: $model_id})
    OPTIONAL MATCH (session)-[:HAS_SYMBOLIC_VALUE]->(value:SymbolicValue)-[:INSTANCE_OF]->(var:SymbolicVariable)<-[:DEFINES_VARIABLE]-(sm)
    OPTIONAL MATCH (value)-[:ABOUT_EXECUTION]->(execution)
    WHERE
        value IS NULL
        OR (
            ($variable_id IS NULL OR coalesce(var.variableId, value.variableId) = $variable_id)
            AND (
                $variable_name IS NULL
                OR toLower(coalesce(var.name, "")) = toLower($variable_name)
            )
        )
    RETURN
        sm.modelId AS modelId,
        sm.version AS version,
        sm.createdAt AS modelCreatedAt,
        sm.updatedAt AS modelUpdatedAt,
        coalesce(sm.isActive, false) AS isActive,
        sm.modelName AS modelName,
        sm.taskDescription AS taskDescription,
        value.valueId AS valueId,
        value.variableId AS variableId,
        var.name AS variableName,
        value.tier AS tier,
        value.type AS type,
        value.value AS value,
        value.reason AS reason,
        value.trajectoryIndex AS trajectoryIndex,
        value.assignmentStrategy AS assignmentStrategy,
        value.createdAt AS createdAt,
        coalesce(execution.executionId, execution.id) AS executionId,
        coalesce(execution.spanId, execution.span_id) AS spanId,
        COALESCE(
            execution.agentName,
            execution.agent_name,
            execution.llmName,
            execution.llm_name,
            execution.modelName,
            execution.toolName,
            execution.tool_name,
            execution.masName,
            execution["mas_name"],
            execution["taskName"],
            execution["task_name"],
            execution.processingName,
            execution.processing_name,
            CASE
                WHEN execution.entityName IS NOT NULL AND execution.entityName <> 'unknown'
                THEN execution.entityName
                ELSE null
            END,
            execution.executionType
        ) AS entityName,
        labels(execution) AS executionLabels
    ORDER BY coalesce(trajectoryIndex, -1), coalesce(createdAt, ""), coalesce(valueId, "")
    """

    if offset > 0:
        query += """
    SKIP $offset
    """

    if limit is not None:
        query += """
    LIMIT $limit
    """

    return query, {
        "session_id": session_id,
        "model_id": model_id,
        "variable_id": variable_id,
        "variable_name": variable_name,
        "limit": limit,
        "offset": offset,
    }
