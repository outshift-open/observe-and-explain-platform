#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
import os
from typing import Any, Dict, Union

from pydantic import ConfigDict, field_validator
from pydantic_settings import BaseSettings

_QUALITY_CATEGORY: Dict[str, dict] = {
    "IntentRecognitionAccuracy": {
        "name": "Intent recognition accuracy",
        "description": "Session-level intent recognition accuracy.",
        "operation": "average",
        "response_key": "intentRecognitionAccuracy",
        "source_metrics": ["IntentRecognitionAccuracy", "IntentRecognition"],
        "unit": "PERCENTAGE",
    },
    "Groundedness": {
        "name": "Groundedness",
        "description": "Session-level groundedness score.",
        "operation": "average",
        "response_key": "groundedness",
        "source_metrics": ["Groundedness", "GroundednessMetric"],
        "unit": "PERCENTAGE",
    },
    "ToolUtilizationAccuracy": {
        "name": "Tool utilization accuracy",
        "description": "Call-level tool utilization accuracy.",
        "operation": "average",
        "response_key": "toolUtilizationAccuracy",
        "source_metrics": ["ToolUtilizationAccuracy"],
        "unit": "PERCENTAGE",
    },
    "deepeval.AnswerRelevancy": {
        "name": "Answer relevancy",
        "description": "Session-level answer relevancy score.",
        "operation": "average",
        "response_key": "answerRelevancy",
        "source_metrics": [
            "deepeval.AnswerRelevancy",
            "AnswerRelevancyMetric",
            "Relevancy",
        ],
        "unit": "PERCENTAGE",
    },
    "PolicySafety": {
        "name": "Policy safety",
        "description": "Session-level policy safety score.",
        "operation": "average",
        "response_key": "policySafety",
        "source_metrics": ["PolicySafety"],
        "unit": "PERCENTAGE",
    },
    "GoalAlignment": {
        "name": "Goal alignment",
        "description": "Session-level goal alignment score.",
        "operation": "average",
        "response_key": "goalAlignment",
        "source_metrics": ["GoalAlignment"],
        "unit": "PERCENTAGE",
    },
    "InstructionFollowing": {
        "name": "Instruction following",
        "description": "Session-level instruction following score.",
        "operation": "average",
        "response_key": "instructionFollowing",
        "source_metrics": ["InstructionFollowing"],
        "unit": "PERCENTAGE",
    },
    "HandoffQuality": {
        "name": "Handoff quality",
        "description": "Session-level handoff quality score.",
        "operation": "average",
        "response_key": "handoffQuality",
        "source_metrics": ["HandoffQuality"],
        "unit": "PERCENTAGE",
    },
    "ConfidenceCalibration": {
        "name": "Confidence calibration",
        "description": "Session-level confidence calibration score.",
        "operation": "average",
        "response_key": "confidenceCalibration",
        "source_metrics": ["ConfidenceCalibration"],
        "unit": "PERCENTAGE",
    },
    "VerificationQuality": {
        "name": "Verification quality",
        "description": "Session-level verification quality score.",
        "operation": "average",
        "response_key": "verificationQuality",
        "source_metrics": ["VerificationQuality"],
        "unit": "PERCENTAGE",
    },
    "CommunicationEfficiency": {
        "name": "Communication efficiency",
        "description": "Session-level communication efficiency score.",
        "operation": "average",
        "response_key": "communicationEfficiency",
        "source_metrics": ["CommunicationEfficiency"],
        "unit": "PERCENTAGE",
    },
    "ConstraintSatisfaction": {
        "name": "Constraint satisfaction",
        "description": "Session-level constraint satisfaction score.",
        "operation": "average",
        "response_key": "constraintSatisfaction",
        "source_metrics": ["ConstraintSatisfaction"],
        "unit": "PERCENTAGE",
    },
    "ResponseCompleteness": {
        "name": "Response completeness",
        "description": "Session-level response completeness score.",
        "operation": "average",
        "response_key": "responseCompleteness",
        "source_metrics": ["ResponseCompleteness"],
        "unit": "PERCENTAGE",
    },
    "MDT": {
        "name": "MDT",
        "description": "Trajectory quality score.",
        "operation": "average",
        "response_key": "trajectoryQuality",
        "source_metrics": ["MDT", "trajectory_score"],
        "unit": "PERCENTAGE",
    },
    "NeuroSymbolicEvaluation": {
        "name": "Neuro-symbolic evaluation",
        "description": "Neuro-symbolic evaluation score when available.",
        "operation": None,
        "is_card": True,
        "response_key": "neuroSymbolicEvaluation",
        "source_metrics": ["NeuroSymbolicEvaluation", "neuro_symbolic_evaluation"],
        "unit": "PERCENTAGE",
    },
}

_RELIABILITY_CATEGORY: Dict[str, dict] = {
    "PassiveEvalAppCompletionRate": {
        "name": "Completion rate",
        "description": "Application completion rate from PassiveEvalApp.",
        "operation": None,
        "is_card": True,
        "response_key": "completionRate",
        "source_metrics": ["PassiveEvalApp"],
        "value_path": ["value", "eval.app.completion_rate"],
        "unit": "PERCENTAGE",
    },
    "Consistency": {
        "name": "Consistency",
        "description": "Consistency score when available.",
        "operation": None,
        "is_card": True,
        "response_key": "consistency",
        "source_metrics": ["Consistency", "SemanticConsistency", "LogicalConsistency"],
        "unit": "PERCENTAGE",
    },
}

_TOOLS_CATEGORY: Dict[str, dict] = {
    "listOfTools": {
        "name": "List of tools",
        "description": "The list of tools used by the agent.",
        "operation": "sum",
        "response_key": "listOfTools",
        "unit": "SCALAR",
    },
}

_PERFORMANCE_CATEGORY: Dict[str, dict] = {
    "WorkflowEfficiency": {
        "name": "Workflow efficiency",
        "description": "Session-level workflow efficiency score.",
        "operation": "average",
        "response_key": "workflowEfficiency",
        "source_metrics": ["WorkflowEfficiency"],
        "unit": "PERCENTAGE",
    },
    "CyclesCount": {
        "name": "Cycle efficiency",
        "description": "Derived as 1 / (1 + CyclesCount).",
        "operation": "average",
        "response_key": "cycleEfficiency",
        "source_metrics": ["CyclesCount"],
        "formula": "inverse_one_plus",
        "unit": "PERCENTAGE",
    },
    "LLMErrorRate": {
        "name": "LLM error rate",
        "description": "Derived from PassiveEvalApp llm_fails / llm_calls.",
        "operation": "average",
        "response_key": "llmErrorRate",
        "source_metrics": ["PassiveEvalApp"],
        "formula": "ratio",
        "numerator_path": ["value", "eval.app.llm_fails"],
        "denominator_path": ["value", "eval.app.llm_calls"],
        "unit": "PERCENTAGE",
    },
    "ToolErrorRate": {
        "name": "Tool error rate",
        "description": "Derived from PassiveEvalApp tool_fails / tool_calls.",
        "operation": "average",
        "response_key": "toolErrorRate",
        "source_metrics": ["PassiveEvalApp"],
        "formula": "ratio",
        "numerator_path": ["value", "eval.app.tool_fails"],
        "denominator_path": ["value", "eval.app.tool_calls"],
        "unit": "PERCENTAGE",
    },
}


# Top-level category constants referenced from _DEFAULT_METRIC_CATEGORIES
_GENERAL_CATEGORY: Dict[str, dict] = {
    "Duration": {
        "name": "Total LLM invocations duration",
        "description": "The total duration of all the LLM invocations for an agent.",
        "operation": "average",
        "response_key": "totalLLMInvocationDuration",
        "unit": "MILLISECONDS",
        "min_value": 0,
        "max_value": 86400000,
    },
    "Cost": {
        "name": "Total agent cost",
        "description": "Sums of LLM and Tools cost.",
        "operation": "sum",
        "response_key": "totalAgentCost",
        "unit": "DOLLAR",
    },
    "GoalSuccessRate": {
        "name": "Overall task completion",
        "description": "Assesses whether the agents successfully achieved the user's goal.",
        "operation": "average",
        "response_key": "overallTaskCompletion",
        "unit": "PERCENTAGE",
    },
    "Relevancy": {
        "name": "Average answer relevancy",
        "description": "Measures how closely the answer aligns to the user query.",
        "operation": "average",
        "response_key": "averageAnswerRelevancy",
        "unit": "PERCENTAGE",
    },
    "successRate": {
        "name": "Completion rate",
        "description": "The completion rate of the agent.",
        "operation": "average",
        "response_key": "successRate",
        "unit": "PERCENTAGE",
    },
}


_COST_CATEGORY: Dict[str, dict] = {
    "Cost": {
        "name": "Total LLM cost",
        "description": "The total cost of LLM operations.",
        "operation": "sum",
        "response_key": "totalLLMCost",
        "unit": "DOLLAR",
    },
    "totalToolCost": {
        "name": "Total tool cost",
        "description": "The total cost of tool operations.",
        "operation": "sum",
        "response_key": "totalToolCost",
        "unit": "DOLLAR",
    },
    "averageLLMCost": {
        "name": "Average LLM cost",
        "description": "The average cost per LLM operation.",
        "operation": "average",
        "response_key": "averageLLMCost",
        "unit": "DOLLAR",
    },
    "averageToolCost": {
        "name": "Average Tool cost",
        "description": "Should be broken down per tool.",
        "operation": "average",
        "response_key": "averageToolCost",
        "unit": "DOLLAR",
    },
    "numberOfLLMCalls": {
        "name": "Number of LLM calls",
        "description": "The total number of LLM calls.",
        "operation": "sum",
        "response_key": "numberOfLLMCalls",
        "unit": "SCALAR",
    },
    "numberOfToolCalls": {
        "name": "Number of tool calls",
        "description": "The total number of tool calls.",
        "operation": "sum",
        "response_key": "numberOfToolCalls",
        "unit": "SCALAR",
    },
}


_LLM_CATEGORY: Dict[str, dict] = {
    "Cost": {
        "name": "Total LLM cost",
        "description": "The total cost of LLM operations.",
        "operation": "sum",
        "response_key": "totalLLMCost",
        "unit": "DOLLAR",
    },
    "TokenCount": {
        "name": "Total tokens",
        "description": "Number of total tokens.",
        "operation": "sum",
        "response_key": "totalTokens",
        "unit": "TOKENS",
    },
    "inputTokens": {
        "name": "Input tokens",
        "description": "Number of input tokens.",
        "operation": "sum",
        "response_key": "inputTokens",
        "unit": "TOKENS",
    },
    "outputTokens": {
        "name": "Output tokens",
        "description": "Number of output tokens.",
        "operation": "sum",
        "response_key": "outputTokens",
        "unit": "TOKENS",
    },
    "Duration": {
        "name": "Inference duration",
        "description": "Duration of the LLM call.",
        "operation": "average",
        "response_key": "inferenceDuration",
        "unit": "MILLISECONDS",
        "min_value": 0,
        "max_value": 3600000,
    },
    "answerCorrectness": {
        "name": "Answer correctness",
        "description": "Measures if the answer if factually correct. (ground truth needed)",
        "operation": "average",
        "response_key": "answerCorrectness",
        "unit": "PERCENTAGE",
    },
    "Relevancy": {
        "name": "Answer relevancy",
        "description": "Measures how closely the answer aligns to the user query.",
        "operation": "average",
        "response_key": "answerRelevancy",
        "unit": "PERCENTAGE",
    },
    "Groundedness": {
        "name": "Answer groundedness",
        "description": "Measures how much the answer is inferred from the given context.",
        "operation": "average",
        "response_key": "answerFaithfulness",
        "unit": "PERCENTAGE",
    },
    "LogicalConsistency": {
        "name": "Coherence",
        "description": "Evaluates whether the response is logically structured, internally consistent, and easy to follow.",
        "operation": "average",
        "response_key": "coherence",
        "unit": "PERCENTAGE",
    },
    "tonality": {
        "name": "Tonality",
        "description": "Evaluates whether the output matches the intended communication style.",
        "operation": "average",
        "response_key": "tonality",
        "unit": "PERCENTAGE",
    },
    "llmErrorRate": {
        "name": "LLM error rate",
        "description": "The rate of error in LLM calls for an agent.",
        "operation": "average",
        "response_key": "llmErrorRate",
        "unit": "PERCENTAGE",
    },
    "llmSuccessRate": {
        "name": "LLM completion rate",
        "description": "The completion rate of LLM calls for an agent.",
        "operation": "average",
        "response_key": "llmSuccessRate",
        "unit": "PERCENTAGE",
    },
    "llmRecoveryRate": {
        "name": "LLM recovery rate",
        "description": "The recovery rate of the LLM calls for an agent.",
        "operation": "average",
        "response_key": "llmRecoveryRate",
        "unit": "PERCENTAGE",
    },
    "llmRetryRate": {
        "name": "LLM retry rate",
        "description": "The rate of retry for a LLM call for an agent.",
        "operation": "average",
        "response_key": "llmRetryRate",
        "unit": "PERCENTAGE",
    },
    "toxicity": {
        "name": "Toxicity",
        "description": "Detects the presence of offensive, harmful, or inappropriate language in model outputs.",
        "operation": "average",
        "response_key": "toxicity",
        "unit": "PERCENTAGE",
    },
    "bias": {
        "name": "Bias",
        "description": "Identifies presence of unwanted bias in LLM outputs.",
        "operation": "average",
        "response_key": "bias",
        "unit": "PERCENTAGE",
    },
}


_CONVERSATION_CATEGORY: Dict[str, dict] = {
    "Relevancy": {
        "name": "Relevancy",
        "description": "Judges if each turn is pertinent and contributes constructively to the overall dialogue flow.",
        "operation": "average",
        "response_key": "relevancy",
        "unit": "PERCENTAGE",
    },
    "ResponseCompleteness": {
        "name": "Completeness",
        "description": "Judges whether the conversation fully addresses user needs, covering all requested points or sub-queries across turns.",
        "operation": "average",
        "response_key": "completeness",
        "unit": "PERCENTAGE",
    },
    "roleAdherence": {
        "name": "Role adherence",
        "description": "Assesses whether the Agent consistently maintains a defined persona, style, or role throughout a conversation.",
        "operation": "average",
        "response_key": "roleAdherence",
        "unit": "PERCENTAGE",
    },
    "IntentRecognition": {
        "name": "Intent recognition accuracy",
        "description": "Measure how well the Assistant understands and correctly identifies user intents.",
        "operation": "average",
        "response_key": "intentRecognitionAccuracy",
        "unit": "PERCENTAGE",
    },
    "GoalSuccessRate": {
        "name": "Goal success rate",
        "description": "Measure how well the Assistant achieves the goals provided by the user.",
        "operation": "average",
        "response_key": "goalSuccessRate",
        "unit": "PERCENTAGE",
    },
}

# Default category → metric definitions.  Override with the
# ``METRIC_CATEGORIES`` env var (JSON object).
# Each metric entry carries:
#   name        – human-readable display name
#   description – short explanation
#   operation   – target aggregation: "sum", "average", or null (card-only)
#   is_card     – whether the metric is a KPI card (no time-series chart)
_DEFAULT_METRIC_CATEGORIES: Dict[str, Dict[str, dict]] = {
    # Keys = Neo4j metricName (PascalCase, used for Cypher queries).
    # ``response_key`` = camelCase key returned to the frontend.
    "general": _GENERAL_CATEGORY,
    "performance": _PERFORMANCE_CATEGORY,
    "quality": _QUALITY_CATEGORY,
    "reliability": _RELIABILITY_CATEGORY,
    "tools": _TOOLS_CATEGORY,
    "cost": _COST_CATEGORY,
    "llm": _LLM_CATEGORY,
    "conversation": _CONVERSATION_CATEGORY,
}


# Optional human-friendly metadata for each category. Kept separate to preserve
# the original shape of `METRIC_CATEGORIES` (mapping -> metric definitions)
# while providing additional fields for UI/clients.
_DEFAULT_METRIC_CATEGORIES_META: Dict[str, Dict[str, Any]] = {
    "general": {
        "name": "General",
        "description": "General session-level metrics",
        "key": "general",
        "metrics_list": list(_GENERAL_CATEGORY.keys()),
    },
    "performance": {
        "name": "Performance",
        "description": "Performance-related metrics",
        "key": "performance",
        "metrics_list": list(_PERFORMANCE_CATEGORY.keys()),
    },
    "quality": {
        "name": "Quality",
        "description": "Quality and evaluation metrics",
        "key": "quality",
        "metrics_list": list(_QUALITY_CATEGORY.keys()),
    },
    "reliability": {
        "name": "Reliability",
        "description": "Reliability and safety metrics",
        "key": "reliability",
        "metrics_list": list(_RELIABILITY_CATEGORY.keys()),
    },
    "tools": {
        "name": "Tools",
        "description": "Tool usage and related metrics",
        "key": "tools",
        "metrics_list": list(_TOOLS_CATEGORY.keys()),
    },
    "cost": {
        "name": "Cost",
        "description": "Cost-related metrics",
        "key": "cost",
        "metrics_list": list(_COST_CATEGORY.keys()),
    },
    "llm": {
        "name": "LLM",
        "description": "LLM-specific metrics",
        "key": "llm",
        "metrics_list": list(_LLM_CATEGORY.keys()),
    },
    "conversation": {
        "name": "Conversation",
        "description": "Conversation-level metrics",
        "key": "conversation",
        "metrics_list": list(_CONVERSATION_CATEGORY.keys()),
    },
}


def resolve_neo4j_auth(
    *,
    default_username: str = "neo4j",
    default_password: str = "",
) -> tuple[str, str]:
    """Resolve Neo4j credentials with NEO4J_AUTH compatibility.

    Priority:
    1) NEO4J_AUTH (username/password)
    2) Legacy split vars (NEO4J_USERNAME/NEO4J_PASSWORD)
    3) Defaults
    """

    auth_username: str | None = None
    auth_password: str | None = None
    neo4j_auth = os.getenv("NEO4J_AUTH")
    if neo4j_auth and "/" in neo4j_auth:
        auth_username, auth_password = neo4j_auth.split("/", 1)

    username = auth_username or os.getenv("NEO4J_USERNAME") or default_username
    password = auth_password or os.getenv("NEO4J_PASSWORD") or default_password
    return username, password


_DEFAULT_NEO4J_USERNAME, _DEFAULT_NEO4J_PASSWORD = resolve_neo4j_auth(
    default_username="neo4j",
    default_password="",
)


class Settings(BaseSettings):
    model_config = ConfigDict(case_sensitive=True)
    API_V1_STR: str = "/api/v1"
    API_V2_STR: str = "/api/v2"
    CLICKHOUSE_HOST: str = os.getenv("CLICKHOUSE_HOST", "localhost")
    CLICKHOUSE_PORT: int = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    CLICKHOUSE_USERNAME: str = os.getenv("CLICKHOUSE_USERNAME", "admin")
    CLICKHOUSE_PASSWORD: str = os.getenv("CLICKHOUSE_PASSWORD", "admin")
    CLICKHOUSE_DATABASE: str = os.getenv("CLICKHOUSE_DATABASE", "default")
    NEO4J_HOST: str = os.getenv("NEO4J_HOST", "localhost")
    NEO4J_PORT: int = int(os.getenv("NEO4J_PORT", "7687"))
    NEO4J_USERNAME: str = _DEFAULT_NEO4J_USERNAME
    NEO4J_PASSWORD: str = _DEFAULT_NEO4J_PASSWORD
    NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "neo4j")

    CACHE_REDIS_URL: str = os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0")
    CACHE_ENABLED: bool = os.getenv("CACHE_ENABLED", "true").lower() == "true"
    CACHE_TTL_SECONDS: int = int(os.getenv("CACHE_TTL_SECONDS", "55"))

    METRIC_CATEGORIES: Dict[str, Dict[str, dict]] = _DEFAULT_METRIC_CATEGORIES
    METRIC_CATEGORIES_META: Dict[str, Dict[str, Any]] = _DEFAULT_METRIC_CATEGORIES_META

    @field_validator("METRIC_CATEGORIES", mode="before")
    def assemble_metric_categories(
        cls, v: Union[str, Dict[str, Dict[str, dict]]]
    ) -> Dict[str, Dict[str, dict]]:
        if isinstance(v, str):
            return json.loads(v)
        return v


settings = Settings()
