#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Shared constants for the client layer."""

# ── Span-detail constants ────────────────────────────────────────────────────

SPAN_TYPE_CHAT = "chat"
SPAN_TYPE_AGENT = "agent"
SPAN_TYPE_TOOL = "tool"

PROMPT_ROLE = "gen_ai.prompt.{}.role"
PROMPT_CONTENT = "gen_ai.prompt.{}.content"
COMPLETION_ROLE = "gen_ai.completion.{}.role"
COMPLETION_CONTENT = "gen_ai.completion.{}.content"

INPUT_TOKENS_KEY = "gen_ai.usage.input_tokens"
OUTPUT_TOKENS_KEY = "gen_ai.usage.output_tokens"
LLM_USAGE_TOTAL_TOKENS = "llm.usage.total_tokens"

COST_PER_TOKEN = 2.5e-6  # dollars per token

KEY_INPUT_TOKENS = "Input Tokens"
KEY_INPUT_COST = "Input Cost"
KEY_OUTPUT_TOKENS = "Output Tokens"
KEY_OUTPUT_COST = "Output Cost"
KEY_TOTAL_TOKENS = "Total Tokens"
KEY_TOTAL_COST = "Total Cost"

SCOPE_NAME_TRACER = "ioa.observe.tracer"
ENTITY_INPUT = "ioa_observe.entity.input"
ENTITY_OUTPUT = "ioa_observe.entity.output"

TRACELOOP_INPUT = "traceloop.entity.input"
TRACELOOP_OUTPUT = "traceloop.entity.output"

CHAT_INPUT = "chat.input"
CHAT_OUTPUT = "chat.output"

INIT_RUN = "__init_run"

ERROR_STATUS = "Error"
EXCEPTION_MESSAGE = "exception.message"

# Number of time periods for monitor application level timeline
PERIODS_COUNT = 12

# Status constants for monitor tasks
TASK_STATUS_DONE = "done"

# Separator constants for agent name display
DASH_SEPARATOR = "-"
SPACE_SEPARATOR = " "

# ── Derived-metrics metric names ─────────────────────────────────────────────

WORKFLOW_EFFICIENCY = "WorkflowEfficiency"
APP_GROUNDEDNESS = "GroundednessMetric"
ANSWER_RELEVANCY = "AnswerRelevancyMetric"
RESPONSE_COMPLETENESS = "ResponseCompleteness"
TOOL_UTILIZATION_ACCURACY = "ToolUtilizationAccuracy"

# Passive eval SDK metric name
PASSIVE_EVAL_APP_METRIC = "PassiveEvalApp"
APP_LLM_COST = "eval.app.llm_cost"
SESSION_DURATION = "eval.app.duration"
APP_LLM_CALLS = "eval.app.llm_calls"
APP_TOOL_CALLS = "eval.app.tool_calls"
APP_LLM_FAILS = "eval.app.llm_fails"
APP_TOOL_FAILS = "eval.app.tool_fails"
APP_GRAPH_DETERMINISM = "eval.app.graph_determinism"
APP_GRAPH_DYNAMISM = "eval.app.graph_dynamism"
APP_RETRIEVAL_LATENCY = "eval.app.retrieval_latency"
APP_AGENT_DURATION = "eval.app.duration"
APP_LLM_INVOCATION_DURATION = "eval.app.llm_invocation_duration"
APP_WORKFLOW_EFFICIENCY = "eval.app.workflow_efficiency"
APP_COMPLETION_RATE = "eval.app.completion_rate"

# MCE metric names (additional)
TOXICITY = "ToxicityMetric"
TONALITY = "TonalityMetric"
CONTEXT_PRESERVATION = "ContextPreservation"
