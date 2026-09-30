#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""LLM judge support for trajectory-context extension metrics."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from metrics_computation_engine.llm_judge.llm import LLMClient

from stateful_evals_be.evaluation.trajectory_context import TrajectoryContext

from .base import EvidenceRef, HighLevelMetricFailure, MetricInputConfig
from .helpers import compact, final_answer_text, selected_claims, selected_evidence


class MetricJudge(Protocol):
    """Judge interface used by LLM-backed high-level metrics."""

    def judge(
        self,
        *,
        metric_name: str,
        rubric: str,
        context_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return a JSON-like metric verdict."""

    def judge_batch(
        self,
        *,
        metrics_payload: Sequence[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Judge several rubrics against one shared artifact payload."""


@dataclass(frozen=True)
class JudgeUsage:
    """Token usage returned by an LLM judge call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_payload(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class LLMMetricJudge:
    """JSON-only LLM judge for high-level trajectory context metrics."""

    _SYSTEM_PROMPT = """\
You are a rigorous evaluator for multi-agent trajectory context.

Judge the requested high-level metric semantically using only the provided
trajectory-context components. Do not use keyword matching or brittle string
patterns. Do not assume domain facts that are not in the context. A policy-
compliant refusal, denial, transfer, or request for more information can be a
passing outcome when it is justified by the provided context.

Evaluate the complete sequence, not an isolated intermediate response, except
when the metric rubric explicitly defines an event-level decision. For
outcome-level metrics, check for later evidence that corrects, supersedes,
verifies, or explicitly preserves the uncertainty of the cited issue. For
event-level metrics, apply the rubric's stated treatment of later recovery.
Treat two claims as contradictory only when they concern the same subject,
scope, time, and operational meaning. The absence of one symptom is not proof
that a broader condition is false.

Recorded operation provenance is authoritative. An operation with
actor_scope="peer" occurred inside a delegated agent execution and must never
be attributed to the root orchestrator. Use agent_id and parent_delegation_id
to evaluate each component only against the instructions available to that
component.

A score of 0 requires at least one fatal failure. Minor issues must receive
score 1. A fully recovered issue must receive score 1 unless the metric
explicitly evaluates whether the earlier event itself was valid. A passing
metric must have an empty fatal_failures list.

Set applicable to false only when the metric rubric states an applicability
condition and the trajectory does not meet it; then return score 1 with no
failures and explain why in reasoning. Otherwise set applicable to true.

Return strict JSON only. No markdown.
"""

    _OUTPUT_SCHEMA = {
        "applicable": "boolean; false only when the rubric's applicability condition is not met",
        "score": "integer 0 or 1; 1 means the metric passes, 0 means it fails",
        "reasoning": "short overall explanation",
        "fatal_failures": [
            {
                "span_index": "integer; use -1 if not clear",
                "entity_name": "component/agent/tool/final_answer name",
                "reasoning": "why this is fatal for the metric",
                "explanation": "specific context-grounded details",
                "observed_impact": "concise snake_case impact label",
                "confidence": "number from 0.0 to 1.0",
                "evidence": [
                    {
                        "span_index": "integer",
                        "source_name": "component/source name",
                        "kind": "claim|fact|intent|final_answer|policy",
                        "content": "brief supporting excerpt",
                    }
                ],
            }
        ],
        "minor_failures": [
            {
                "span_index": "integer; use -1 if not clear",
                "entity_name": "component/agent/tool/final_answer name",
                "reasoning": "why this is minor or self-corrected",
                "explanation": "specific context-grounded details",
                "observed_impact": "concise snake_case impact label",
                "confidence": "number from 0.0 to 1.0",
                "evidence": [],
            }
        ],
        "metadata": "optional object with judge notes; keep small",
    }

    _BATCH_OUTPUT_SCHEMA = {
        "metrics": [
            {
                "high_level_metric": "exact metric name from the request",
                "applicable": "boolean; false only when the rubric's applicability condition is not met",
                "score": "integer 0 or 1",
                "reasoning": "one sentence, 60 words maximum",
                "evidence_refs": "array of 1-3 exact artifact_id strings supporting the verdict",
                "fatal_failures": [
                    {
                        "span_index": "integer; use -1 if unclear",
                        "entity_name": "component/agent/tool/final_answer name",
                        "reasoning": "one concise, evidence-grounded sentence",
                        "evidence_refs": "array of 1-3 exact artifact_id strings from trajectory_context",
                    }
                ],
                "minor_failures": [
                    {
                        "span_index": "integer; use -1 if unclear",
                        "entity_name": "component/agent/tool/final_answer name",
                        "reasoning": "one concise, evidence-grounded sentence",
                        "evidence_refs": "array of 1-3 exact artifact_id strings from trajectory_context",
                    }
                ],
            }
        ]
    }

    def __init__(
        self,
        llm_client: LLMClient | Any | None = None,
        *,
        model_name: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        max_tokens: int = 4096,
        max_attempts: int = 3,
        retry_max_tokens: int = 16384,
        reasoning_effort: str | None = "low",
    ) -> None:
        self.model_name = model_name or os.getenv(
            "LLM_MODEL_NAME", "bedrock/global.anthropic.claude-sonnet-4-6"
        )
        self.base_url = base_url or os.getenv("LLM_BASE_MODEL_URL", "")
        self.api_key = (
            api_key
            or os.getenv("LLM_API_KEY", "")
            or os.getenv("LITELLM_PROXY_API_KEY", "")
        )
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = LLMClient(
                {
                    "LLM_MODEL_NAME": self.model_name,
                    "LLM_BASE_MODEL_URL": self.base_url,
                    "LLM_API_KEY": self.api_key,
                }
            )
        self.last_usage = JudgeUsage()
        self.max_tokens = max(512, int(max_tokens))
        self.max_attempts = max(1, int(max_attempts))
        self.retry_max_tokens = max(
            self.max_tokens,
            int(retry_max_tokens),
        )
        self.last_attempt_count = 0
        self.last_finish_reason = ""
        self.reasoning_effort = reasoning_effort

    def _query_kwargs(self, *, max_tokens: int | None = None) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "temperature": (
                1.0 if "claude-sonnet" in self.model_name.casefold() else 0.0
            ),
            "max_tokens": max_tokens or self.max_tokens,
        }
        if self.reasoning_effort:
            kwargs["reasoning_effort"] = self.reasoning_effort
        return kwargs

    def _query_json(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        initial_max_tokens: int,
    ) -> Mapping[str, Any]:
        usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        last_error: Exception | None = None
        self.last_attempt_count = 0
        self.last_finish_reason = ""
        for attempt in range(self.max_attempts):
            attempt_messages = [dict(message) for message in messages]
            if attempt:
                attempt_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous response was empty, truncated, or invalid "
                            "JSON. Retry with strict compact JSON only. Keep overall "
                            "reasoning under 60 words, return at most one fatal and "
                            "one minor failure per metric, and cite artifact IDs "
                            "instead of copying evidence excerpts."
                        ),
                    }
                )
            attempt_max_tokens = min(
                self.retry_max_tokens,
                initial_max_tokens * (2**attempt),
            )
            response = self.llm_client.query(
                attempt_messages,
                **self._query_kwargs(max_tokens=attempt_max_tokens),
            )
            self.last_attempt_count = attempt + 1
            choice = response.choices[0]
            content = choice.message.content or ""
            self.last_finish_reason = str(getattr(choice, "finish_reason", "") or "")
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(
                getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
            )
            usage_totals["prompt_tokens"] += prompt_tokens
            usage_totals["completion_tokens"] += completion_tokens
            usage_totals["total_tokens"] += total_tokens
            try:
                parsed = parse_judge_json(content)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                continue
            self.last_usage = JudgeUsage(**usage_totals)
            return parsed

        self.last_usage = JudgeUsage(**usage_totals)
        detail = (
            f" after {self.last_attempt_count} attempt(s)"
            f" (finish_reason={self.last_finish_reason or 'unknown'})"
        )
        raise ValueError(f"Judge did not return valid JSON{detail}") from last_error

    def judge(
        self,
        *,
        metric_name: str,
        rubric: str,
        context_payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        user_prompt = json.dumps(
            {
                "metric_name": metric_name,
                "rubric": rubric,
                "trajectory_context": context_payload,
                "output_schema": self._OUTPUT_SCHEMA,
            },
            ensure_ascii=True,
            default=str,
        )
        return self._query_json(
            (
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ),
            initial_max_tokens=self.max_tokens,
        )

    def judge_batch(
        self,
        *,
        metrics_payload: Sequence[Mapping[str, Any]],
        shared_context: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Judge several rubrics once against a deduplicated artifact store."""
        user_prompt = json.dumps(
            {
                "task": (
                    "Evaluate every requested metric independently. Each metric "
                    "lists the shared artifact components it may inspect. Resolve "
                    "evidence references against the shared trajectory context. "
                    "Keep each reasoning under 60 words. Check later artifacts and "
                    "the final answer for evidence that resolves or supersedes an "
                    "earlier issue. For a passing metric, return no fatal failures; "
                    "minor recovered findings are allowed with score 1. Score 0 "
                    "requires exactly one fatal failure. For a failing metric, return at "
                    "most one failure. For every metric, cite 1-3 exact artifact_id "
                    "values in its evidence_refs; failed findings may cite their own "
                    "evidence_refs too. Emit only fields declared in output_schema. Do not "
                    "include evidence excerpts, explanations, metadata, or additional "
                    "prose."
                ),
                "trajectory_context": shared_context,
                "metrics": list(metrics_payload),
                "output_schema": self._BATCH_OUTPUT_SCHEMA,
            },
            ensure_ascii=True,
            default=str,
        )
        return self._query_json(
            (
                {"role": "system", "content": self._SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ),
            initial_max_tokens=max(self.max_tokens, 16384),
        )


def parse_judge_json(raw_text: str) -> Mapping[str, Any]:
    """Parse JSON from a judge response."""
    text = (raw_text or "").strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        for start, character in enumerate(text):
            if character != "{":
                continue
            try:
                parsed, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                return parsed
        raise original_error
    if not isinstance(parsed, Mapping):
        raise ValueError("Judge response must be a JSON object")
    return parsed


def build_context_payload(
    context: TrajectoryContext,
    input_config: MetricInputConfig,
    *,
    metric_name: str,
    max_item_chars: int | None = None,
) -> dict[str, Any]:
    """Build the selected trajectory-context slice for an LLM rubric."""
    payload: dict[str, Any] = {
        "metric_name": metric_name,
        "input_config": input_config.to_payload(),
        "coordination_context": context.coordination_context.topology_payload(),
    }
    evidence_indexes = {id(fact): index for index, fact in enumerate(context.evidence)}
    intent_indexes = {id(intent): index for index, intent in enumerate(context.intents)}
    claim_indexes = {id(claim): index for index, claim in enumerate(context.claims)}
    if input_config.includes("policy"):
        payload["policy"] = _content(context.policy_text, max_item_chars)
        payload["policy_artifact_id"] = "policy:root"
        payload["semantic_contracts"] = [
            {
                "span_index": fact.span_index,
                "source_name": fact.source_name,
                "content": _content(fact.content, max_item_chars),
                "artifact_id": fact.source_name,
            }
            for fact in context.evidence
            if fact.fact_type == "policy_rule"
            and fact.source_name.startswith("semantic_contract:")
        ]
    if input_config.includes("user_statements"):
        payload["user_statements"] = [
            {
                **_fact_payload(fact, max_item_chars=max_item_chars),
                "artifact_id": f"user:{evidence_indexes[id(fact)]}",
            }
            for fact in selected_evidence(context, input_config)
            if fact.fact_type == "user_statement"
        ]
    if input_config.includes("fact_store"):
        payload["fact_store"] = [
            {
                **_fact_payload(fact, max_item_chars=max_item_chars),
                "artifact_id": f"fact:{evidence_indexes[id(fact)]}",
            }
            for fact in selected_evidence(context, input_config)
            if fact.fact_type not in {"policy_rule", "user_statement"}
        ]
    if input_config.includes("intents"):
        payload["intents"] = [
            {
                "name": intent.name,
                "description": intent.description,
                "requirement_type": intent.requirement_type,
                "source": intent.source,
                "first_seen": intent.first_seen,
                "last_seen": intent.last_seen,
                "status": intent.status,
                "owner_agent_ids": getattr(intent, "owner_agent_ids", []),
                "assigned_by_agent_id": getattr(
                    intent,
                    "assigned_by_agent_id",
                    "",
                ),
                "assignment_mode": getattr(intent, "assignment_mode", ""),
                "parent_intent_ids": getattr(intent, "parent_intent_ids", []),
                "dependency_intent_ids": getattr(
                    intent,
                    "dependency_intent_ids",
                    [],
                ),
                "expected_output": _content(
                    getattr(intent, "expected_output", ""),
                    max_item_chars,
                ),
                "phase": getattr(intent, "phase", ""),
                "round_index": getattr(intent, "round_index", None),
                "events": _compact_intent_events(
                    intent.events,
                    max_item_chars=max_item_chars,
                    available_components=input_config.components,
                ),
                "artifact_id": f"intent:{intent_indexes[id(intent)]}",
            }
            for intent in context.intents
        ]
    if input_config.includes("claims"):
        payload["claims"] = [
            {
                "span_index": claim.span_index,
                "claim_type": claim.claim_type,
                "entity_name": claim.entity_name,
                "agent_id": getattr(claim, "agent_id", ""),
                "actor_scope": getattr(claim, "actor_scope", ""),
                "span_id": getattr(claim, "span_id", ""),
                "parent_span_id": getattr(claim, "parent_span_id", ""),
                "trace_id": getattr(claim, "trace_id", ""),
                "related_intent_ids": getattr(claim, "related_intent_ids", []),
                "evidence_refs": getattr(claim, "evidence_refs", []),
                "revision_of_claim_id": getattr(
                    claim,
                    "revision_of_claim_id",
                    "",
                ),
                "phase": getattr(claim, "phase", ""),
                "round_index": getattr(claim, "round_index", None),
                "content": _content(claim.content, max_item_chars),
                "artifact_id": f"claim:{claim_indexes[id(claim)]}",
            }
            for claim in selected_claims(context, input_config)
        ]
    if input_config.includes("final_answer"):
        final_limit = None if max_item_chars is None else max(5000, max_item_chars)
        payload["final_answer"] = _content(
            final_answer_text(context, input_config),
            final_limit,
        )
        payload["final_answer_artifact_id"] = "final_answer"
        payload["final_answer_span_index"] = context.latest_root_answer_span_index
    if input_config.includes("operations"):
        operations, summary = build_operation_context(
            context,
            max_item_chars=max_item_chars,
        )
        payload["operations"] = operations
        payload["coordination_summary"] = summary
        payload["work_ledger"] = [
            {
                "artifact_id": f"intent:{index}",
                "name": intent.name,
                "description": _content(intent.description, max_item_chars),
                "status": intent.status,
                "owner_agent_ids": getattr(intent, "owner_agent_ids", []),
                "assigned_by_agent_id": getattr(
                    intent,
                    "assigned_by_agent_id",
                    "",
                ),
                "assignment_mode": getattr(intent, "assignment_mode", ""),
                "parent_intent_ids": getattr(intent, "parent_intent_ids", []),
                "dependency_intent_ids": getattr(
                    intent,
                    "dependency_intent_ids",
                    [],
                ),
                "expected_output": _content(
                    getattr(intent, "expected_output", ""),
                    max_item_chars,
                ),
                "phase": getattr(intent, "phase", ""),
                "round_index": getattr(intent, "round_index", None),
            }
            for index, intent in enumerate(context.intents)
        ]
        payload["coordination_events"] = [
            {
                "artifact_id": event.event_id,
                "span_index": event.span_index,
                "event_type": event.event_type,
                "operation_name": event.operation_name,
                "actor_agent_id": event.actor_agent_id,
                "sender_agent_ids": event.sender_agent_ids,
                "recipient_agent_ids": event.recipient_agent_ids,
                "related_intent_ids": event.related_intent_ids,
                "input_artifact_ids": event.input_artifact_ids,
                "output_artifact_ids": event.output_artifact_ids,
                "linked_span_ids": event.linked_span_ids,
                "link_types": event.link_types,
                "assignment_mode": event.assignment_mode,
                "status": event.status,
                "content": (
                    ""
                    if event.input_artifact_ids or event.output_artifact_ids
                    else _content(event.content, max_item_chars)
                ),
                "phase": event.phase,
                "round_index": event.round_index,
                "span_id": event.span_id,
                "parent_span_id": event.parent_span_id,
                "trace_id": event.trace_id,
            }
            for event in getattr(context, "coordination_events", [])
        ]
        # Direct content and lineage are already encoded on intents, claims,
        # facts, and coordination events. Keep only relationships that are not
        # recoverable from those canonical records; the persisted
        # TrajectoryContext retains every edge and its span metadata.
        payload["provenance_links"] = [
            {
                "source_artifact_id": link.source_artifact_id,
                "target_artifact_id": link.target_artifact_id,
                "relation_type": link.relation_type,
            }
            for link in getattr(context, "provenance_links", [])
            if link.relation_type
            not in {
                "advances",
                "informs",
                "produces",
                "supports",
                "assigns",
                "communicates",
            }
        ]
        payload["provenance_link_scope"] = (
            "Non-redundant links only; direct inputs, outputs, intent progress, "
            "and claim support are encoded on canonical artifacts."
        )
        payload["coordination_metadata"] = dict(
            getattr(context, "coordination_metadata", {})
        )
        delegation_audit, delegation_summary = build_delegation_context(
            context,
            operations=operations,
            max_item_chars=max_item_chars,
        )
        payload["delegation_audit"] = delegation_audit
        payload["delegation_summary"] = delegation_summary
        if _normalise_agent_id(metric_name) == "instruction_following":
            payload["instruction_execution_audit"] = (
                build_instruction_execution_context(
                    context,
                    operations=operations,
                )
            )
    return payload


def build_operation_context(
    context: TrajectoryContext,
    *,
    max_item_chars: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Derive an actor-scoped operation history from accumulated state.

    New trajectory contexts carry span provenance directly. Older artifacts
    retain enough information to recover scope from claim types, semantic
    contract boundaries, and delegation order.
    """
    evidence_indexes = {id(fact): index for index, fact in enumerate(context.evidence)}
    claim_indexes = {id(claim): index for index, claim in enumerate(context.claims)}
    rows_by_span: dict[int, dict[str, Any]] = {}

    for fact in context.evidence:
        if fact.fact_type != "tool_output":
            continue
        row = rows_by_span.setdefault(
            fact.span_index,
            {
                "span_index": fact.span_index,
                "operation_type": "tool",
                "entity_name": fact.source_name,
                "artifact_id": f"operation:{fact.span_index}",
                "evidence_refs": [],
                "content_parts": [],
                "claim_type": "",
                "agent_id": getattr(fact, "agent_id", ""),
                "actor_scope": getattr(fact, "actor_scope", ""),
                "span_id": getattr(fact, "span_id", ""),
                "parent_span_id": getattr(fact, "parent_span_id", ""),
                "trace_id": getattr(fact, "trace_id", ""),
            },
        )
        row["operation_type"] = "tool"
        row["entity_name"] = fact.source_name
        row["evidence_refs"].append(f"fact:{evidence_indexes[id(fact)]}")
        row["content_parts"].append(fact.content)
        row["outcome"] = getattr(fact, "outcome", "")
        row["started_at_ns"] = getattr(fact, "started_at_ns", None)
        row["duration_ns"] = getattr(fact, "duration_ns", None)

    for claim in context.claims:
        if claim.claim_type == "tool_result":
            continue
        row = rows_by_span.setdefault(
            claim.span_index,
            {
                "span_index": claim.span_index,
                "operation_type": "llm",
                "entity_name": claim.entity_name,
                "artifact_id": f"operation:{claim.span_index}",
                "evidence_refs": [],
                "content_parts": [],
                "claim_type": claim.claim_type,
                "agent_id": getattr(claim, "agent_id", ""),
                "actor_scope": getattr(claim, "actor_scope", ""),
                "span_id": getattr(claim, "span_id", ""),
                "parent_span_id": getattr(claim, "parent_span_id", ""),
                "trace_id": getattr(claim, "trace_id", ""),
            },
        )
        row["claim_type"] = claim.claim_type or row.get("claim_type", "")
        for key in (
            "agent_id",
            "actor_scope",
            "span_id",
            "parent_span_id",
            "trace_id",
        ):
            value = getattr(claim, key, "")
            if value:
                row[key] = value
        row["evidence_refs"].append(f"claim:{claim_indexes[id(claim)]}")
        row["content_parts"].append(claim.content)

    for event in getattr(context, "coordination_events", []):
        row = rows_by_span.setdefault(
            event.span_index,
            {
                "span_index": event.span_index,
                "operation_type": "coordination",
                "entity_name": event.operation_name,
                "artifact_id": f"operation:{event.span_index}",
                "evidence_refs": [],
                "content_parts": [],
                "claim_type": "",
                "agent_id": event.actor_agent_id,
                "actor_scope": "",
                "span_id": event.span_id,
                "parent_span_id": event.parent_span_id,
                "trace_id": event.trace_id,
            },
        )
        row.setdefault("coordination_event_ids", []).append(event.event_id)
        row.setdefault("coordination_event_types", []).append(event.event_type)
        row.setdefault("sender_agent_ids", []).extend(event.sender_agent_ids)
        row.setdefault("recipient_agent_ids", []).extend(event.recipient_agent_ids)
        row.setdefault("related_intent_ids", []).extend(event.related_intent_ids)
        row.setdefault("linked_span_ids", []).extend(event.linked_span_ids)
        row.setdefault("link_types", []).extend(event.link_types)
        if event.round_index is not None:
            row["round_index"] = event.round_index
        if event.phase:
            row["phase"] = event.phase
        if event.content and not row["content_parts"]:
            row["content_parts"].append(event.content)

    contract_agents = sorted(
        (
            fact.span_index,
            fact.source_name.split(":", 1)[1],
        )
        for fact in context.evidence
        if fact.fact_type == "policy_rule"
        and fact.source_name.startswith("semantic_contract:")
    )
    root_claims = sorted(
        (
            claim
            for claim in context.claims
            if claim.claim_type != "peer_agent_assertion"
            and claim.claim_type != "tool_result"
        ),
        key=lambda claim: claim.span_index,
    )
    root_agent_id = next(
        (
            str(getattr(claim, "agent_id", "") or "")
            for claim in root_claims
            if getattr(claim, "agent_id", "")
        ),
        "",
    )
    if not root_agent_id and root_claims:
        root_span = root_claims[0].span_index
        root_agent_id = next(
            (agent for span, agent in contract_agents if span == root_span),
            "",
        )
    if not root_agent_id and contract_agents:
        root_agent_id = contract_agents[0][1]
    root_agent_id = root_agent_id or "root"

    def contract_agent_at(span_index: int) -> str:
        candidates = [
            agent
            for contract_span, agent in contract_agents
            if contract_span <= span_index
        ]
        return candidates[-1] if candidates else ""

    work_by_request_span = {
        unit.request_span_index: unit
        for unit in getattr(context, "work_units", [])
        if unit.request_span_index >= 0
    }
    work_request_spans = set(work_by_request_span)
    operations: list[dict[str, Any]] = []
    active_delegations: dict[str, dict[str, str]] = {}
    latest_delegation: dict[str, str] | None = None
    current_agent_id = root_agent_id
    current_actor_scope = "root"
    for span_index in sorted(rows_by_span):
        row = rows_by_span[span_index]
        for key in (
            "evidence_refs",
            "coordination_event_ids",
            "coordination_event_types",
            "sender_agent_ids",
            "recipient_agent_ids",
            "related_intent_ids",
            "linked_span_ids",
            "link_types",
        ):
            if key in row:
                row[key] = list(dict.fromkeys(row[key]))
        content = "\n".join(str(item) for item in row.pop("content_parts") if item)
        entity_name = str(row.get("entity_name") or "")
        operation_type = str(row.get("operation_type") or "")
        claim_type = str(row.get("claim_type") or "")
        actor_scope = str(row.get("actor_scope") or "")
        if not actor_scope:
            if claim_type == "peer_agent_assertion":
                actor_scope = "peer"
            elif claim_type:
                actor_scope = "root"
            else:
                actor_scope = current_actor_scope

        agent_id = str(row.get("agent_id") or "")
        if not agent_id:
            if actor_scope == "root":
                agent_id = root_agent_id
            elif claim_type == "peer_agent_assertion":
                inferred_agent = contract_agent_at(span_index)
                if inferred_agent and _normalise_agent_id(
                    inferred_agent
                ) != _normalise_agent_id(root_agent_id):
                    agent_id = inferred_agent
                elif latest_delegation is not None:
                    agent_id = latest_delegation["recipient_agent_id"]
            else:
                agent_id = current_agent_id
        agent_id = agent_id or ("peer" if actor_scope == "peer" else root_agent_id)

        coordination_event_types = {
            str(item) for item in row.get("coordination_event_types", []) if str(item)
        }
        is_delegation = bool(coordination_event_types & {"assignment", "handoff"}) or (
            operation_type == "tool" and span_index in work_request_spans
        )
        input_match = re.search(
            r"Called with:\s*(?P<input>.*?)(?:\n\s*Returned:|\Z)",
            content,
            re.IGNORECASE | re.DOTALL,
        )
        input_signature = (
            " ".join(input_match.group("input").split())[:500] if input_match else ""
        )

        parent_delegation = None
        if actor_scope == "peer":
            parent_delegation = active_delegations.get(_normalise_agent_id(agent_id))
            if parent_delegation is None:
                parent_delegation = latest_delegation

        row.update(
            {
                "claim_type": claim_type,
                "agent_id": agent_id,
                "actor_scope": actor_scope,
                "parent_delegation_id": (
                    parent_delegation["delegation_id"]
                    if parent_delegation is not None
                    else ""
                ),
                "delegator_agent_id": (
                    parent_delegation["delegator_agent_id"]
                    if parent_delegation is not None
                    else ""
                ),
                "recipient_agent_id": (
                    parent_delegation["recipient_agent_id"]
                    if parent_delegation is not None
                    else ""
                ),
            }
        )
        if is_delegation:
            normalized_recipients = [
                str(item) for item in row.get("recipient_agent_ids", []) if str(item)
            ]
            request_unit = work_by_request_span.get(span_index)
            if not normalized_recipients and request_unit is not None:
                normalized_recipients = [
                    str(item) for item in request_unit.recipient_agent_ids if str(item)
                ]
            recipient_agent_id = (
                normalized_recipients[0]
                if normalized_recipients
                else _delegation_recipient(entity_name)
            )
            delegation = {
                "delegation_id": f"delegation:{span_index}",
                "delegator_agent_id": agent_id,
                "recipient_agent_id": recipient_agent_id,
            }
            row.update(delegation)
            active_delegations[_normalise_agent_id(recipient_agent_id)] = delegation
            latest_delegation = delegation

        started_at_ns = row.pop("started_at_ns", None)
        duration_ns = row.pop("duration_ns", None)
        if started_at_ns is not None:
            row["started_at"] = _format_epoch_ns(started_at_ns)
            if duration_ns is not None:
                row["ended_at"] = _format_epoch_ns(started_at_ns + duration_ns)
        work_unit = work_by_request_span.get(span_index) if is_delegation else None
        if work_unit is not None:
            row["work_id"] = work_unit.work_id
            row["work_outcome"] = work_unit.outcome
        operations.append(
            {
                **row,
                "is_delegation": is_delegation,
                "input_signature": input_signature,
                "content": _content(
                    content,
                    None if max_item_chars is None else min(max_item_chars, 420),
                ),
            }
        )
        current_agent_id = agent_id
        current_actor_scope = actor_scope

    repeated_calls = _exact_repeated_call_groups(operations)
    tool_operations = [item for item in operations if item["operation_type"] == "tool"]
    coordination_events = list(getattr(context, "coordination_events", []))
    return operations, {
        "total_operations": len(operations),
        "llm_operations": len(operations) - len(tool_operations),
        "tool_operations": len(tool_operations),
        "delegation_operations": sum(1 for item in operations if item["is_delegation"]),
        "root_operations": sum(
            1 for item in operations if item["actor_scope"] == "root"
        ),
        "peer_operations": sum(
            1 for item in operations if item["actor_scope"] == "peer"
        ),
        "unscoped_operations": sum(
            1 for item in operations if item["actor_scope"] not in {"root", "peer"}
        ),
        "exact_repeated_call_groups": repeated_calls,
        "exact_repeated_call_count": sum(
            max(0, int(item["count"]) - 1) for item in repeated_calls
        ),
        "coordination_event_count": len(coordination_events),
        "coordination_event_counts": {
            event_type: sum(
                1 for event in coordination_events if event.event_type == event_type
            )
            for event_type in sorted(
                {event.event_type for event in coordination_events}
            )
        },
        "topology": getattr(context, "coordination_metadata", {}).get(
            "topology",
            "",
        ),
    }


def _exact_repeated_call_groups(
    operations: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Group tool calls by agent, tool, and exact input.

    Each call carries its outcome, the outcome of the call before it in the
    group, its start and end times, and its parent span and delegation, so a
    retry after a failure or a nested call is distinguishable from waste.
    """
    groups: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for operation in operations:
        if operation.get("operation_type") != "tool" or not operation.get(
            "input_signature"
        ):
            continue
        groups.setdefault(
            (
                str(operation.get("agent_id") or "").casefold(),
                str(operation.get("entity_name") or "").casefold(),
                str(operation.get("input_signature") or "").casefold(),
            ),
            [],
        ).append(operation)

    repeated = []
    for group in groups.values():
        if len(group) < 2:
            continue
        calls = []
        previous: Mapping[str, Any] | None = None
        for operation in group:
            parent_span_id = str(operation.get("parent_span_id") or "")
            call = {
                "span_index": _safe_int(operation.get("span_index"), -1),
                "artifact_id": str(operation.get("artifact_id") or ""),
                "span_id": str(operation.get("span_id") or ""),
                "parent_span_id": parent_span_id,
                "parent_delegation_id": str(
                    operation.get("parent_delegation_id") or ""
                ),
                "started_at": str(operation.get("started_at") or ""),
                "ended_at": str(operation.get("ended_at") or ""),
                "outcome": str(
                    operation.get("work_outcome") or operation.get("outcome") or ""
                ),
            }
            if previous is not None:
                call["previous_call_outcome"] = str(
                    previous.get("work_outcome") or previous.get("outcome") or ""
                )
                call["relation_to_previous_call"] = (
                    "child_of_previous_call"
                    if parent_span_id
                    and parent_span_id == str(previous.get("span_id") or "")
                    else "same_parent_span"
                    if parent_span_id
                    and parent_span_id == str(previous.get("parent_span_id") or "")
                    else "different_parent_span"
                )
            calls.append(call)
            previous = operation
        first = group[0]
        repeated.append(
            {
                "agent_id": str(first.get("agent_id") or ""),
                "entity_name": str(first.get("entity_name") or ""),
                "input_signature": str(first.get("input_signature") or ""),
                "span_indices": [call["span_index"] for call in calls],
                "count": len(calls),
                "calls": calls,
            }
        )
    return repeated


def _format_epoch_ns(value: int) -> str:
    """Render an epoch-nanosecond timestamp as UTC ISO 8601."""
    seconds, nanoseconds = divmod(int(value), 1_000_000_000)
    stamp = datetime.fromtimestamp(seconds, tz=timezone.utc)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S") + f".{nanoseconds // 1000:06d}Z"


def build_instruction_execution_context(
    context: TrajectoryContext,
    *,
    operations: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize delegation attempts and their recorded outcomes."""
    if operations is None:
        operations, _ = build_operation_context(context)

    root_agent_id = next(
        (
            str(operation.get("agent_id") or "")
            for operation in operations
            if operation.get("actor_scope") == "root" and operation.get("agent_id")
        ),
        "root",
    )
    available_peer_agents = sorted(
        {
            _normalise_agent_id(fact.source_name.split(":", 1)[1])
            for fact in context.evidence
            if fact.fact_type == "policy_rule"
            and fact.source_name.startswith("semantic_contract:")
            and _normalise_agent_id(fact.source_name.split(":", 1)[1])
            != _normalise_agent_id(root_agent_id)
        }
    )
    work_by_request_span = {
        unit.request_span_index: unit
        for unit in getattr(context, "work_units", [])
        if unit.request_span_index >= 0
    }
    delegation_attempts = []
    for operation in operations:
        if not operation.get("is_delegation"):
            continue
        span_index = _safe_int(operation.get("span_index"), -1)
        work_unit = work_by_request_span.get(span_index)
        tool_fact = _operation_tool_fact(context, operation)
        delegation_attempts.append(
            {
                "delegation_id": str(operation.get("delegation_id") or ""),
                "span_index": span_index,
                "delegator_agent_id": str(
                    operation.get("delegator_agent_id")
                    or operation.get("agent_id")
                    or ""
                ),
                "recipient_agent_id": str(
                    operation.get("recipient_agent_id")
                    or _delegation_recipient(str(operation.get("entity_name") or ""))
                ),
                "work_id": work_unit.work_id if work_unit is not None else "",
                "attempt_index": (
                    work_unit.attempt_index if work_unit is not None else None
                ),
                "retry_of_work_id": (
                    work_unit.retry_of_work_id if work_unit is not None else ""
                ),
                "retry_basis": work_unit.retry_basis if work_unit is not None else "",
                "outcome": work_unit.outcome if work_unit is not None else "",
                "tool_outcome": tool_fact.outcome if tool_fact is not None else "",
                "result": compact(
                    _delegation_result(str(operation.get("content") or "")), 360
                ),
                "artifact_id": str(operation.get("artifact_id") or ""),
            }
        )

    attempted_peer_agents = sorted(
        {
            _normalise_agent_id(attempt["recipient_agent_id"])
            for attempt in delegation_attempts
            if attempt["recipient_agent_id"]
        }
    )
    return {
        "available_peer_agents": available_peer_agents,
        "attempted_peer_agents": attempted_peer_agents,
        "delegation_attempt_count_by_agent": {
            agent_id: sum(
                1
                for attempt in delegation_attempts
                if _normalise_agent_id(attempt["recipient_agent_id"]) == agent_id
            )
            for agent_id in attempted_peer_agents
        },
        "delegation_attempts": delegation_attempts,
        "adjudication_rules": {
            "attempt_counts_as_use": True,
            "infrastructure_failure_is_not_instruction_violation": True,
            "recovery_is_required_only_when_explicitly_instructed": True,
        },
    }


def _operation_tool_fact(
    context: TrajectoryContext,
    operation: Mapping[str, Any],
) -> Any | None:
    """Return the tool fact an operation row was built from, if any."""
    for ref in operation.get("evidence_refs") or []:
        kind, _, index = str(ref).partition(":")
        if kind != "fact" or not index.isdigit():
            continue
        position = int(index)
        if position < len(context.evidence):
            fact = context.evidence[position]
            if fact.fact_type == "tool_output":
                return fact
    return None


def build_instruction_following_context(
    context: TrajectoryContext,
    *,
    max_item_chars: int | None = None,
) -> dict[str, Any]:
    """Build a focused instruction view without duplicating full model payloads."""
    operations, coordination_summary = build_operation_context(
        context,
        max_item_chars=max_item_chars,
    )
    execution_audit = build_instruction_execution_context(
        context,
        operations=operations,
    )
    evidence_indexes = {id(fact): index for index, fact in enumerate(context.evidence)}
    semantic_contracts = [
        {
            "span_index": fact.span_index,
            "source_name": fact.source_name,
            "content": _content(fact.content, max_item_chars),
            "artifact_id": fact.source_name,
        }
        for fact in context.evidence
        if fact.fact_type == "policy_rule"
        and fact.source_name.startswith("semantic_contract:")
    ]
    user_statements = [
        {
            **_fact_payload(fact, max_item_chars=max_item_chars),
            "artifact_id": f"user:{evidence_indexes[id(fact)]}",
        }
        for fact in context.evidence
        if fact.fact_type == "user_statement"
    ]
    authoritative_tool_outputs = [
        {
            **_fact_payload(fact, max_item_chars=max_item_chars),
            "artifact_id": f"fact:{evidence_indexes[id(fact)]}",
        }
        for fact in context.evidence
        if fact.fact_type == "tool_output"
    ]
    return {
        "instruction_execution_audit": execution_audit,
        "decision_protocol": {
            "attempt_rule": (
                "instruction_execution_audit lists every delegation attempt with "
                "its recorded outcome. An attempted call counts as use of that "
                "agent even when its outcome is failed or no_response."
            ),
            "absence_rule": (
                "Telemetry that does not expose private reasoning is not positive "
                "evidence that required reasoning was omitted."
            ),
            "completion_boundary": (
                "Missing output after an attempted call belongs to Task Completion or "
                "Constraint Satisfaction unless the component falsely claims completion."
            ),
            "constraint_check": (
                "When an available instruction requires checking a constraint, "
                "compare each displayed final-plan item with the complete "
                "authoritative tool outputs and user statements. A direct "
                "unresolved conflict with that instruction is fatal."
            ),
            "ontology_scope_rule": (
                "A definition scoped to one object does not prohibit discussing a related "
                "object; fail only if the defined term is actually applied outside its scope."
            ),
        },
        "root_policy": _content(context.policy_text, None),
        "root_policy_artifact_id": "policy:root",
        "semantic_contracts": semantic_contracts,
        "user_statements": user_statements,
        "final_answer": final_answer_text(context, MetricInputConfig()),
        "final_answer_artifact_id": "final_answer",
        "final_answer_span_index": context.latest_root_answer_span_index,
        "authoritative_tool_outputs": authoritative_tool_outputs,
        "actor_scoped_operations": operations,
        "coordination_summary": coordination_summary,
    }


def build_delegation_context(
    context: TrajectoryContext,
    *,
    operations: Sequence[Mapping[str, Any]] | None = None,
    max_item_chars: int | None = None,
    include_contract_text: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Pair each delegation with its recipient and every agent's capabilities.

    Capability evidence is structural: the tools bound to or executed by each
    agent, the capability line a roster table declares for it, and, when
    ``include_contract_text`` is set, the lines of its own contract that no
    other agent's contract repeats.
    """
    if operations is None:
        operations, _ = build_operation_context(
            context,
            max_item_chars=max_item_chars,
        )

    contracts = {
        _normalise_agent_id(fact.source_name.split(":", 1)[1]): fact
        for fact in context.evidence
        if fact.fact_type == "policy_rule"
        and fact.source_name.startswith("semantic_contract:")
    }
    evidence_indexes = {id(fact): index for index, fact in enumerate(context.evidence)}
    tool_facts = [fact for fact in context.evidence if fact.fact_type == "tool_output"]
    work_by_request_span = {
        unit.request_span_index: unit
        for unit in getattr(context, "work_units", [])
        if unit.request_span_index >= 0
    }

    audits: list[dict[str, Any]] = []
    for operation in operations:
        if not operation.get("is_delegation"):
            continue
        entity_name = str(operation.get("entity_name") or "")
        recipient = str(
            operation.get("recipient_agent_id") or ""
        ) or _delegation_recipient(entity_name)
        contract = contracts.get(_normalise_agent_id(recipient))
        start_span = _safe_int(operation.get("span_index"), -1)
        delegation_id = str(
            operation.get("delegation_id") or f"delegation:{start_span}"
        )
        observed_tools = []
        for candidate in operations:
            if (
                candidate.get("operation_type") != "tool"
                or candidate.get("is_delegation")
                or candidate.get("parent_delegation_id") != delegation_id
            ):
                continue
            candidate_span = _safe_int(candidate.get("span_index"), -1)
            fact = next(
                (
                    item
                    for item in tool_facts
                    if item.span_index == candidate_span
                    and _normalise_agent_id(item.source_name)
                    == _normalise_agent_id(str(candidate.get("entity_name") or ""))
                ),
                None,
            )
            observed_tools.append(
                {
                    "span_index": candidate_span,
                    "tool_name": str(candidate.get("entity_name") or ""),
                    "agent_id": str(candidate.get("agent_id") or ""),
                    "actor_scope": str(candidate.get("actor_scope") or ""),
                    "parent_delegation_id": delegation_id,
                    "outcome": fact.outcome if fact is not None else "",
                    "content": _content(
                        fact.content if fact is not None else candidate.get("content"),
                        None if max_item_chars is None else min(max_item_chars, 360),
                    ),
                    "artifact_id": (
                        f"fact:{evidence_indexes[id(fact)]}"
                        if fact is not None
                        else str(candidate.get("artifact_id") or "")
                    ),
                }
            )
        delegation_fact = next(
            (
                fact
                for fact in tool_facts
                if fact.span_index == start_span
                and _normalise_agent_id(fact.source_name)
                == _normalise_agent_id(entity_name)
            ),
            None,
        )
        work_unit = work_by_request_span.get(start_span)
        audits.append(
            {
                "delegation_id": delegation_id,
                "operation_artifact_id": str(operation.get("artifact_id") or ""),
                "span_index": start_span,
                "delegator_agent_id": str(
                    operation.get("delegator_agent_id")
                    or operation.get("agent_id")
                    or ""
                ),
                "actor_scope": str(operation.get("actor_scope") or ""),
                "recipient_agent": recipient,
                "delegated_task": _delegated_task(
                    str(operation.get("input_signature") or "")
                ),
                "delegation_result": _delegation_result(
                    delegation_fact.content if delegation_fact is not None else ""
                ),
                "delegation_outcome": (
                    work_unit.outcome
                    if work_unit is not None
                    else delegation_fact.outcome
                    if delegation_fact is not None
                    else ""
                ),
                "work_id": work_unit.work_id if work_unit is not None else "",
                "recipient_contract_artifact_id": (
                    contract.source_name if contract is not None else ""
                ),
                "observed_tools_before_next_delegation": observed_tools,
            }
        )

    summary: dict[str, Any] = {
        "delegation_count": len(audits),
        "delegations_with_contract": sum(
            1 for audit in audits if audit["recipient_contract_artifact_id"]
        ),
        "agent_capabilities": _agent_capability_profiles(
            context,
            contracts,
            include_contract_text=include_contract_text,
            max_item_chars=max_item_chars,
        ),
        "capability_precedence": (
            "Tool-backed and demonstrated capabilities outrank routing or ownership "
            "assertions in mutable policy text."
        ),
        "recovery_rule": (
            "A later recovery may protect the final outcome but does not erase an "
            "executed material wrong-owner delegation."
        ),
        "decision_protocol": (
            "For each delegation, split the delegated task into material capability "
            "requirements. Match every requirement to the recipient's tools "
            "(declared_tools, observed_tools, observed_tools_before_next_delegation) "
            "or its agent-specific contract text in agent_capabilities. For a "
            "requirement the recipient cannot support, check the other agents in "
            "agent_capabilities. Record a fatal wrong-owner delegation only when "
            "another available agent has direct support for the same action and "
            "object. A capability absent from every agent is a system coverage gap, "
            "not a routing error. Work already completed by its capable owner and "
            "repeated as context in a later task is not a new wrong-owner "
            "delegation unless the later task asks for independent verification."
        ),
    }
    tool_definitions = getattr(context, "tool_definitions", None)
    if include_contract_text and tool_definitions:
        summary["tool_definitions"] = _content(
            json.dumps(tool_definitions, ensure_ascii=True, default=str),
            None if max_item_chars is None else max(max_item_chars, 4000),
        )
    return audits, summary


def _agent_capability_profiles(
    context: TrajectoryContext,
    contracts: Mapping[str, Any],
    *,
    include_contract_text: bool,
    max_item_chars: int | None,
) -> list[dict[str, Any]]:
    """Describe each agent by its tools and, optionally, its own contract text."""
    profiles = {
        _normalise_agent_id(agent_id): profile
        for agent_id, profile in (getattr(context, "agents", None) or {}).items()
    }
    specific_text = (
        _agent_specific_contract_text(contracts) if include_contract_text else {}
    )
    rows = []
    for agent_id in dict.fromkeys([*profiles, *contracts]):
        profile = profiles.get(agent_id)
        contract = contracts.get(agent_id)
        if profile is not None and not getattr(profile, "active", True):
            continue
        row: dict[str, Any] = {
            "agent_id": profile.agent_id if profile is not None else agent_id,
            "contract_artifact_id": (
                contract.source_name if contract is not None else ""
            ),
            "declared_tools": list(getattr(profile, "declared_tools", []) or []),
            "observed_tools": list(getattr(profile, "observed_tools", []) or []),
            "declared_capability": str(
                getattr(profile, "declared_capability", "") or ""
            ),
            "declared_capability_source": str(
                getattr(profile, "declared_capability_source", "") or ""
            ),
        }
        if include_contract_text and contract is not None:
            row["agent_specific_contract_text"] = _content(
                specific_text.get(agent_id, ""),
                max_item_chars,
            )
        rows.append(row)
    return rows


def _agent_specific_contract_text(contracts: Mapping[str, Any]) -> dict[str, str]:
    """Keep the contract lines that appear in only one agent's contract.

    Text repeated verbatim across contracts, such as a shared skill or protocol
    section, describes the system rather than one agent, so it is not evidence
    of that agent's own capability.
    """

    def units(content: str) -> list[str]:
        if "\n" in content:
            return content.splitlines()
        return re.split(r"(?<=[.!?])\s+", content)

    owners: dict[str, set[str]] = {}
    for agent_id, fact in contracts.items():
        for unit in units(fact.content):
            key = " ".join(unit.split())
            if key:
                owners.setdefault(key, set()).add(agent_id)
    return {
        agent_id: "\n".join(
            unit.rstrip()
            for unit in units(fact.content)
            if " ".join(unit.split()) and len(owners[" ".join(unit.split())]) == 1
        )
        for agent_id, fact in contracts.items()
    }


def _normalise_agent_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).casefold()).strip("_")


def _delegation_recipient(entity_name: str) -> str:
    normalized = _normalise_agent_id(entity_name)
    if normalized.startswith("delegate_to_"):
        return normalized.removeprefix("delegate_to_")
    return normalized


def _delegated_task(input_signature: str) -> str:
    try:
        payload = json.loads(input_signature)
    except (json.JSONDecodeError, TypeError):
        return compact(input_signature, 1400)
    task = _find_nested_task(payload)
    if task:
        return compact(task, 1400)
    return compact(input_signature, 1400)


def _find_nested_task(value: Any, *, depth: int = 0) -> str:
    if depth > 4:
        return ""
    if isinstance(value, Mapping):
        task = value.get("task")
        if task is not None:
            nested_task = _find_nested_task(task, depth=depth + 1)
            if nested_task:
                return nested_task
            return str(task)
        for key in ("arguments", "input", "input_payload", "payload"):
            if key in value:
                nested = _find_nested_task(value[key], depth=depth + 1)
                if nested:
                    return nested
        return ""
    if isinstance(value, str):
        try:
            nested_value = json.loads(value)
        except json.JSONDecodeError:
            return ""
        return _find_nested_task(nested_value, depth=depth + 1)
    return ""


def _delegation_result(content: str) -> str:
    if not content:
        return ""
    match = re.search(r"\bReturned:\s*(?P<result>.*)\Z", content, re.DOTALL)
    return compact(match.group("result") if match else content, 700)


def build_shared_context_payload(
    context: TrajectoryContext,
    input_configs: Sequence[MetricInputConfig],
    *,
    supplemental_context: Mapping[str, Any] | None = None,
    max_item_chars: int | None = None,
) -> dict[str, Any]:
    """Build one canonical artifact store shared by every batched rubric.

    Metric payloads contain only their rubric and allowed component names.  The
    policy, intents, facts, claims, and final answer occur exactly once in the
    LLM request instead of once per metric.
    """
    components = frozenset(
        component for config in input_configs for component in config.components
    )
    claim_limits = [
        config.max_claims for config in input_configs if config.max_claims is not None
    ]
    fact_limits = [
        config.max_facts for config in input_configs if config.max_facts is not None
    ]
    union_config = MetricInputConfig(
        components=components,
        max_claims=max(claim_limits, default=None),
        max_facts=max(fact_limits, default=None),
    )
    payload = build_context_payload(
        context,
        union_config,
        metric_name="shared_trajectory_audit",
        max_item_chars=max_item_chars,
    )
    payload.pop("metric_name", None)
    if supplemental_context:
        payload["stateful_signals"] = _compact_supplemental_context(
            supplemental_context,
            max_item_chars=max_item_chars,
        )
    return payload


def resolve_batch_evidence_refs(
    raw_result: Mapping[str, Any],
    shared_context: Mapping[str, Any],
) -> dict[str, Any]:
    """Resolve compact judge artifact IDs into full local evidence references."""
    artifact_lookup: dict[str, dict[str, Any]] = {}
    component_kinds = {
        "user_statements": "fact",
        "fact_store": "fact",
        "direct_tool_evidence": "fact",
        "delegation_outputs": "claim",
        "intents": "intent",
        "claims": "claim",
        "semantic_contracts": "policy",
        "operations": "operation",
        "coordination_events": "coordination",
        "work_ledger": "intent",
    }
    for component, kind in component_kinds.items():
        for item in shared_context.get(component) or []:
            if not isinstance(item, Mapping) or not item.get("artifact_id"):
                continue
            span_index = item.get(
                "span_index", item.get("last_seen", item.get("first_seen", -1))
            )
            artifact_lookup[str(item["artifact_id"])] = {
                "artifact_id": str(item["artifact_id"]),
                "span_index": _safe_int(span_index, -1),
                "source_name": str(
                    item.get("source_name")
                    or item.get("entity_name")
                    or item.get("operation_name")
                    or item.get("name")
                    or component
                ),
                "kind": kind,
                "content": compact(
                    str(item.get("content") or item.get("description") or ""), 400
                ),
            }
    if shared_context.get("policy"):
        artifact_lookup["policy:root"] = {
            "artifact_id": "policy:root",
            "span_index": -1,
            "source_name": "policy",
            "kind": "policy",
            "content": compact(str(shared_context["policy"]), 400),
        }
    if shared_context.get("final_answer"):
        artifact_lookup["final_answer"] = {
            "artifact_id": "final_answer",
            "span_index": _safe_int(shared_context.get("final_answer_span_index"), -1),
            "source_name": "final_answer",
            "kind": "final_answer",
            "content": compact(str(shared_context["final_answer"]), 400),
        }

    resolved = dict(raw_result)
    resolved["evidence"] = [
        artifact_lookup[str(artifact_id)]
        for artifact_id in _safe_list(raw_result.get("evidence_refs"))
        if str(artifact_id) in artifact_lookup
    ]
    for failure_key in ("fatal_failures", "minor_failures"):
        failures = []
        for failure in _safe_list(raw_result.get(failure_key)):
            if not isinstance(failure, Mapping):
                continue
            normalized = dict(failure)
            references = []
            for artifact_id in _safe_list(failure.get("evidence_refs")):
                reference = artifact_lookup.get(str(artifact_id))
                if reference is not None:
                    references.append(reference)
            if references:
                normalized["evidence"] = references
            failures.append(normalized)
        resolved[failure_key] = failures
    return resolved


def normalize_judge_failures(
    metric_name: str,
    failures: Sequence[Mapping[str, Any]],
    *,
    default_classification: str,
) -> list[HighLevelMetricFailure]:
    """Convert judge failure dicts into stable metric failure payloads."""
    normalized: list[HighLevelMetricFailure] = []
    for failure in failures:
        normalized.append(
            HighLevelMetricFailure(
                classification=default_classification,
                high_level_metric=metric_name,
                span_index=_safe_int(failure.get("span_index"), -1),
                entity_name=str(failure.get("entity_name") or ""),
                reasoning=str(failure.get("reasoning") or ""),
                explanation=str(failure.get("explanation") or ""),
                observed_impact=str(failure.get("observed_impact") or ""),
                confidence=_safe_float(failure.get("confidence"), 0.7),
                evidence=normalize_judge_evidence(failure.get("evidence")),
            )
        )
    return normalized


def normalize_judge_evidence(value: Any) -> list[EvidenceRef]:
    """Normalize locally resolved context references into stable payloads."""
    return [
        EvidenceRef(
            span_index=_safe_int(ref.get("span_index"), -1),
            source_name=str(ref.get("source_name") or ""),
            kind=str(ref.get("kind") or ""),
            content=compact(str(ref.get("content") or ""), 400),
            artifact_id=str(ref.get("artifact_id") or ""),
        )
        for ref in _safe_list(value)
        if isinstance(ref, Mapping)
    ]


def judge_usage_payload(judge: MetricJudge) -> dict[str, int]:
    usage = getattr(judge, "last_usage", None)
    if isinstance(usage, JudgeUsage):
        return usage.to_payload()
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def _fact_payload(fact: Any, *, max_item_chars: int | None) -> dict[str, Any]:
    return {
        "span_index": fact.span_index,
        "fact_type": fact.fact_type,
        "source_name": fact.source_name,
        "agent_id": getattr(fact, "agent_id", ""),
        "actor_scope": getattr(fact, "actor_scope", ""),
        "span_id": getattr(fact, "span_id", ""),
        "parent_span_id": getattr(fact, "parent_span_id", ""),
        "trace_id": getattr(fact, "trace_id", ""),
        "related_intent_ids": getattr(fact, "related_intent_ids", []),
        "content": _content(fact.content, max_item_chars),
    }


def _compact_sequence(
    items: Sequence[Any],
    max_item_chars: int | None,
) -> list[Any]:
    compacted: list[Any] = []
    for item in items:
        if isinstance(item, Mapping):
            compacted.append(
                {
                    str(key): (
                        _content(str(value), max_item_chars)
                        if isinstance(value, str)
                        else value
                    )
                    for key, value in item.items()
                }
            )
        else:
            compacted.append(_content(str(item), max_item_chars))
    return compacted


def _compact_intent_events(
    items: Sequence[Any],
    *,
    max_item_chars: int | None,
    available_components: frozenset[str],
) -> list[Any]:
    """Project intent history without repeating canonical artifact content."""
    compacted: list[Any] = []
    for item in items:
        if not isinstance(item, Mapping):
            compacted.append(_content(str(item), max_item_chars))
            continue

        event = dict(item)
        event_type = str(event.get("type") or "")
        canonical_components: list[str] = []
        omitted_keys: set[str] = set()

        if event_type == "tool_attempt" and (
            "operations" in available_components or "fact_store" in available_components
        ):
            omitted_keys.update({"input", "output"})
            canonical_components.extend(
                component
                for component in ("operations", "fact_store")
                if component in available_components
            )
        if event_type == "final_answer_alignment" and (
            "final_answer" in available_components or "claims" in available_components
        ):
            omitted_keys.add("content")
            canonical_components.extend(
                component
                for component in ("final_answer", "claims")
                if component in available_components
            )
        if event_type in {"requirement_observed", "user_restatement"} and (
            "user_statements" in available_components
        ):
            omitted_keys.add("content")
            canonical_components.append("user_statements")

        projected = {
            str(key): (
                _content(str(value), max_item_chars)
                if isinstance(value, str)
                else value
            )
            for key, value in event.items()
            if key not in omitted_keys
        }
        if omitted_keys:
            projected["canonical_content_components"] = list(
                dict.fromkeys(canonical_components)
            )
        compacted.append(projected)
    return compacted


def _compact_supplemental_context(
    value: Mapping[str, Any],
    *,
    max_item_chars: int | None,
) -> dict[str, Any]:
    """Bound optional primitive/final signals without copying full span payloads."""
    compacted: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            compacted[str(key)] = _content(item, max_item_chars)
        elif isinstance(item, list):
            compacted[str(key)] = _compact_sequence(item[:30], max_item_chars)
        elif isinstance(item, Mapping):
            compacted[str(key)] = _compact_supplemental_context(
                item,
                max_item_chars=max_item_chars,
            )
        elif isinstance(item, (bool, int, float)) or item is None:
            compacted[str(key)] = item
        else:
            compacted[str(key)] = _content(str(item), max_item_chars)
    return compacted


def _content(value: Any, max_chars: int | None) -> str:
    """Return lossless context unless a caller explicitly requests a preview."""
    text = str(value)
    return text if max_chars is None else compact(text, max_chars)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, parsed))


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
