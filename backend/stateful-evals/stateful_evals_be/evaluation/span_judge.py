#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Combined per-span judging, prompt preparation and response parsing."""

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any, Dict, List, Optional

from stateful_evals_be.evaluation.json_response import loads_json_response
from stateful_evals_be.evaluation.span_context import current_agent_instruction_records
from stateful_evals_be.evaluation.span_normalization import SpanNormalizer
from stateful_evals_be.models.requests import TemporalMetricOptions

_SPAN_STATE_DELTA_SYSTEM_PROMPT = """\
You evaluate one transition in an accumulated agent trajectory. Judge every
requested primitive from the same compact current-span delta and prior state.

Groundedness: pass when material output claims are supported by provided facts,
policy, or clearly marked uncertainty; fail fabricated or contradicted claims.
IntentRecognition: pass when the transition correctly recognizes and advances
the active user/delegated intent; fail missed, distorted, or abandoned intent.
Relevancy: pass when the transition is relevant and logically compatible with
the active intent and prior claims; fail material contradiction or non-progress.

Assess the current agent's responsibility from its attributed instructions and
observed interactions. Instruction sources identify root policy, the current
agent's instructions, or earlier recorded instructions. Identical text
may have multiple sources. Do not apply another agent's instructions to the
current agent merely because they appear in context. Responsibilities can
include moderating, routing, reviewing, or synthesizing work; infer their meaning
from the full instructions and recorded flow, not special names or phrases.
Assigning or proposing work does not establish that it was executed. Quoted or
relayed material is not automatically the current agent's own assertion.
Accumulated evaluator state is not the acting agent's memory. Establish access
from its recorded call-time input, contract, or supported communication. An
operation's output is available only from its observed_at time. Do not credit a
decision with another operation's result returned after the decision's call
began. Missing completion or status does not establish a successful operation
or a returned result.
An unknown role or outcome alone is not a failure. When deciding a requested
metric requires missing earlier evidence, set `needs_more_context` to true if
that field is available in the output schema.

Return strict JSON only with a `metrics` array. Each item must contain the exact
requested `metric_name`, binary numeric `score`, and one concise `reasoning`.
"""

_LEGACY_RESPONSE_INSTRUCTIONS = """\
Optionally include a compact `state_delta` object with new claims, intent status
updates, and evidence links. Do not restate the supplied context.
"""

_FOCUSED_RESPONSE_INSTRUCTIONS = """\
Do not restate the supplied context. Keep each reasoning to one sentence.
When selection metadata is present, the context is a retrieved view. Omitted
evidence is not proof of absent evidence: set `needs_more_context` to true if
you cannot decide without additional earlier artifacts. Judge a transition
against evidence available at that step, not hypothetical later results.
"""

_FOCUSED_TRANSITION_INSTRUCTIONS = """\
Assess this transition, not whether the whole task is already complete. An
intermediate tool call may address one part of a multi-step request; remaining
work alone is not a Groundedness, IntentRecognition, or Relevancy failure.
Fail abandonment only when the current action actually drops or contradicts a
requirement, or claims completion without satisfying it. A proposed tool call
is an action request, not a claim that its result has already been obtained.
Its concrete record identifiers and factual arguments must still match the
available evidence or documented tool contract. A plausible invented identifier
is not grounded. Distinguish existing-record references from legitimate search
queries or identifiers the tool explicitly allows the caller to create.
When argument_evidence is provided, compare requested_values with observed_values
for existing-record lookups. Different exact IDs are not interchangeable merely
because they describe the same subject. These are observations, not a closed list
of every valid ID; consult the referenced artifact and tool instructions before
deciding whether a mismatch is an error or needs more context.
source_outcome=error identifies a failed response, not a validated reference.
unknown means the outcome is not established. echoed_request_values are values
also present in that source call's arguments; repetition alone does not validate
them. Use the full source record to distinguish returned data from error echoes.
"""


class SpanJudgeError(RuntimeError):
    def __init__(self, message, *, usage, calls):
        super().__init__(message)
        self.usage, self.calls = usage, calls


_EXTRACTION_INSTRUCTIONS = """\
Also organize this observed span into coarse trajectory artifacts and return
state_delta according to state_update_guidance. Keep whole responses as claims,
tool results as evidence, requests/requirements as intents, and observed work
and transfers as work/coordination records. Tool-loaded instructions may add
requirements during execution. Attribute policies and responses to their agents.
Infer ownership and intent links from meaning, including moderation and synthesis.
Separate proposed actions from executed work, peer assertions from direct evidence,
and external requests from delegated tasks. Record uncertainty rather than inventing
roles, evidence or relationships. Preserve canonical IDs, numbers, units, conditions,
provenance, and uncertainty by selecting exact source nodes. All prior intents are
available. Reuse existing records; append new records with consecutive IDs starting
at new_record_ids. Record the actual root request/policy and final user-facing answer
when available. Never turn every response into separate propositions.
The output template describes fields, not records to invent. Use empty lists
for absent updates, actual source IDs and supported values for real records.
"""


def _metric_state_view(prior: dict[str, Any], metric_name: str) -> dict[str, Any]:
    """Project existing ledgers without inferring intent, roles or behavior."""
    ledgers = {
        "IntentRecognition": ("intents", "agents", "work_units"),
        "Groundedness": ("intents", "agents", "claims", "evidence"),
        "Relevancy": ("intents", "agents", "work_units", "claims"),
    }.get(metric_name.split(".")[-1])
    if ledgers is None:
        return prior
    records = {name: rows for name, rows in prior["records"].items() if name in ledgers}
    # Explicit contract relationships retain instruction sources for every judge.
    contracts = {ref for agent in records.get("agents", []) for ref in agent.get("contract_ids", [])}
    for name, rows in prior["records"].items():
        if name not in records and any(row["id"] in contracts for row in rows):
            records[name] = [row for row in rows if row["id"] in contracts]
    index_fields = {
        "id", "artifact_id", "name", "fact_type", "source_name", "claim_type",
        "entity_name", "operation_type", "event_type", "agent_id", "actor_scope",
        "owner_agent_ids", "allocator_agent_id", "recipient_agent_ids",
        "related_intent_ids", "parent_intent_ids", "intent_id", "work_id",
        "evidence_refs", "revision_of_claim_id", "content_ref", "status", "outcome",
        "span_index", "first_seen", "last_seen", "request_span_index",
        "response_span_index", "started_at", "observed_at", "observation_complete",
        "observation_status", "is_delegation", "delegation_id", "span_id", "parent_span_id",
    }

    def index(row):
        return {key: value for key, value in row.items()
                if key in index_fields and value not in (None, "", [], {})}

    view = {
        "records": records,
        "new_record_ids": prior["new_record_ids"],
        "artifact_index": {name: [index(row) for row in rows if row not in records.get(name, [])]
                           for name, rows in prior["records"].items()},
        "operations": [index(row) for row in prior["operations"]],
        "metadata": prior["metadata"],
        "context_view": metric_name,
    }
    sources = prior["selected_source_texts"]
    selected = {}

    def retain_sources(value):
        if isinstance(value, str) and value in sources:
            selected[value] = sources[value]
        elif isinstance(value, dict):
            for item in value.values():
                retain_sources(item)
        elif isinstance(value, list):
            for item in value:
                retain_sources(item)

    retain_sources(records)
    retain_sources(view["metadata"])
    view["selected_source_texts"] = selected
    return view


class SpanJudge:
    """Judge one transition using the caller-owned model query function."""

    def __init__(
        self,
        *,
        query: Callable[..., Any],
        options: TemporalMetricOptions,
        metric_names: list[str],
    ) -> None:
        self._query = query
        self.options = options
        self.metric_names = list(metric_names)

    async def aevaluate_and_update(self, state, *, span_index, raw_span):
        """Run the three judges together, then apply one accepted state update."""
        state.source_catalog(span_index)
        prior = state.prompt_state()
        extractor = next((name for name in self.metric_names
                          if name.split(".")[-1] == "IntentRecognition"), self.metric_names[0])
        payload = {"current_span_index": span_index, "current_raw_span": raw_span}

        async def judge_metric(name):
            extracting = name == extractor
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            request = {**payload, "trajectory_state_before_span": _metric_state_view(prior, name),
                       "requested_metrics": [name],
                       "output_schema": {"metric_name": name, "score": "numeric0or1",
                                         "reasoning": "one concise evidence-grounded sentence"}}
            if extracting:
                request["available_current_sources"] = state.source_catalog(span_index)
                request["observed_instruction_sources"] = state.instruction_sources(span_index)
                request["observed_agent_id"] = SpanNormalizer.resolve_agent_id(raw_span)
                request["state_update_guidance"] = state.schema()
                request["output_schema"]["state_delta"] = {
                    "evidence": [{"id": "fact:N", "source_ref": "catalog source_id",
                                  "fact_type": "policy_rule|tool_output|agent_response|other",
                                  "agent_id": "observed recipient/author ID", "source_name": "source name"}],
                    "claims": [{"id": "claim:N", "source_ref": "catalog source_id",
                                "claim_type": "model-assigned type", "entity_name": "author",
                                "agent_id": "declared agent ID", "related_intent_ids": []}],
                    "intents": [{"id": "intent:N", "source_ref": "catalog source_id",
                                 "name": "short task name", "source": "user or peer_agent",
                                 "status": "in_progress", "owner_agent_ids": [], "parent_intent_ids": []}],
                    "agents": [{"id": "stable agent ID", "source_ref": "catalog source_id",
                                "contract_ids": ["existing or same-delta policy_rule fact ID"]}],
                    "work_units": [{"id": "work:N", "source_ref": "catalog source_id",
                                    "allocator_agent_id": "declared agent ID", "recipient_agent_ids": [],
                                    "intent_id": "existing or same-delta intent ID"}],
                    "coordination_events": [{"id": "coordination:N", "source_ref": "catalog source_id",
                                             "event_type": "observed event", "operation_name": "operation"}],
                    "operation": {"operation_type": "llm|tool|coordination", "entity_name": "operation name",
                                  "agent_id": "observed_agent_id or null if unknown",
                                  "actor_scope": "root|peer|unknown", "is_delegation": False},
                    "metadata": {"root_agent_id": "root agent ID or null if not known",
                                 "policy_text_ref": "root instruction source ID or null if unchanged",
                                 "root_request_ref": "external request source ID or null if unchanged",
                                 "final_answer_ref": "root response source ID or null if unchanged"},
                }
            messages = [{"role": "system", "content": (
                _SPAN_STATE_DELTA_SYSTEM_PROMPT.partition("Return strict JSON only")[0]
                + _FOCUSED_TRANSITION_INSTRUCTIONS
                + (_EXTRACTION_INSTRUCTIONS if extracting else "")
                + "Artifact indexes provide identity and provenance, not omitted source content. "
                "Use records and selected_source_texts for supporting content; an indexed claim "
                "or unfinished operation is not verified evidence. "
                + "Return one strict JSON object for only the requested metric using output_schema."
            )}, {"role": "user", "content": json.dumps(request, ensure_ascii=False, default=str)}]
            error = None
            for attempt in range(self.options.span_judge_max_attempts):
                text = None
                try:
                    response = await self._query(
                        messages,
                        max_tokens=min(16384, (self.options.span_judge_max_tokens
                                              if extracting else 1024) * (2**attempt)),
                        response_format={"type": "json_object"},
                    )
                    for key in usage:
                        usage[key] += int(getattr(getattr(response, "usage", None), key, 0) or 0)
                    text = (response.choices[0].message.content or "").strip()
                    if text.startswith("```"):
                        text = text.split("\n", 1)[1].removesuffix("```").strip()
                    result = loads_json_response(text, allow_eof_close=getattr(response.choices[0], "finish_reason", None) == "stop")
                    if isinstance(result, dict) and set(result) == {name} and isinstance(result[name], dict):
                        result = result[name]
                    if isinstance(result, dict):
                        result.setdefault("metric_name", name)
                    if not isinstance(result, dict) or result.get("metric_name") != name:
                        raise ValueError(f"Return metric_name={name!r}")
                    if type(result.get("score")) not in (int, float) or result["score"] not in (0, 1):
                        raise ValueError("score must be numeric0or1")
                    if not isinstance(result.get("reasoning"), str) or not result["reasoning"].strip():
                        raise ValueError("reasoning must be nonempty")
                    if extracting:
                        state.validate(result.get("state_delta"), span_index, raw_span)
                    return {"result": result, "usage": usage, "calls": attempt + 1}
                except (ValueError, TypeError, KeyError, IndexError) as exc:
                    error = exc
                    if text:
                        messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user", "content": (
                        f"Previous response rejected: {exc}. State has not changed. "
                        "Return complete corrected JSON. Use catalog source IDs only for content "
                        "pointers; relationship fields require record IDs. "
                        "Preserve valid state_delta records and fields; declare any new "
                        "referenced record in the same delta or reuse an available ID."
                    )})
                except Exception as exc:
                    raise SpanJudgeError(str(exc), usage=usage, calls=attempt + 1) from exc
            raise SpanJudgeError(f"Span{span_index} {name} failed: {error}",
                                 usage=usage, calls=self.options.span_judge_max_attempts)

        verdicts = await asyncio.gather(*(judge_metric(name) for name in self.metric_names),
                                        return_exceptions=True)
        usage = {key: sum((v.usage if isinstance(v, SpanJudgeError) else v["usage"]).get(key, 0)
                          for v in verdicts) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
        calls = sum(v.calls if isinstance(v, SpanJudgeError) else v["calls"] for v in verdicts)
        errors = [v for v in verdicts if isinstance(v, Exception)]
        if errors:
            raise SpanJudgeError(str(errors[0]), usage=usage, calls=calls)
        results = [v["result"] for v in verdicts]
        state.apply(next(row["state_delta"] for row in results if row["metric_name"] == extractor),
                    span_index, raw_span)
        return {"metrics": results, "usage": usage, "calls": calls}

    @staticmethod
    def compact_value(value: Any, max_chars: int | None) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            text = " ".join(value.split())
        else:
            try:
                text = json.dumps(value, ensure_ascii=False, default=str)
            except Exception:
                text = str(value)
        if max_chars is None or len(text) <= max_chars:
            if not isinstance(value, str):
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    pass
            return text
        return text[: max_chars - 22] + "... [truncated]"

    def prepare_span(self, span_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Keep only current-turn I/O; never forward accumulated prompt history."""
        input_payload = span_dict.get("input_payload")
        output_payload = span_dict.get("output_payload")
        focused = self.options.span_context_mode == "focused"
        message_limit = None if focused else 1600
        messages: List[Dict[str, str]] = []

        if isinstance(input_payload, dict):
            indexed: Dict[int, Dict[str, str]] = {}
            role_re = re.compile(r"^gen_ai\.prompt\.(\d+)\.role$")
            content_re = re.compile(r"^gen_ai\.prompt\.(\d+)\.content$")
            for key, value in input_payload.items():
                match = role_re.match(str(key))
                if match:
                    indexed.setdefault(int(match.group(1)), {})["role"] = str(value)
                    continue
                match = content_re.match(str(key))
                if match:
                    indexed.setdefault(int(match.group(1)), {})["content"] = (
                        SpanNormalizer._normalize_text(value)
                    )
            messages = [
                {
                    "role": entry.get("role", "user").lower(),
                    "content": str(entry.get("content", ""))[:message_limit],
                }
                for _, entry in sorted(indexed.items())
                if entry.get("content")
                and entry.get("role", "user").lower() != "system"
            ]

        if not messages:
            for message_list in SpanNormalizer._iter_message_lists(input_payload):
                for message in message_list:
                    parsed = SpanNormalizer._extract_message_entry(message)
                    if parsed and parsed["role"] != "system":
                        parsed["content"] = parsed["content"][:message_limit]
                        messages.append(parsed)

        max_messages = int(self.options.max_messages or 2)
        current_input: Any = messages[-max_messages:]
        if not current_input:
            current_input = self.compact_value(input_payload, None if focused else 2400)

        output_texts: List[str] = []
        if isinstance(output_payload, dict):
            completion_re = re.compile(r"^gen_ai\.completion\.(\d+)\.content$")
            indexed_output = sorted(
                (
                    int(match.group(1)),
                    SpanNormalizer._normalize_text(value),
                )
                for key, value in output_payload.items()
                if (match := completion_re.match(str(key)))
            )
            output_texts = [
                text[: None if focused else 2400] for _, text in indexed_output if text
            ]
        current_output: Any = output_texts[-1] if output_texts else None
        if current_output is None:
            current_output = self.compact_value(
                output_payload, None if focused else 3000
            )

        prepared = {
            "span_id": span_dict.get("span_id", ""),
            "agent_id": span_dict.get("agent_id") or None,
            "entity_type": span_dict.get("entity_type", ""),
            "entity_name": span_dict.get("entity_name", ""),
            "contains_error": bool(span_dict.get("contains_error")),
            "current_input": current_input,
            "current_output": current_output,
        }
        if not focused:
            prepared["instructions"] = current_agent_instruction_records(span_dict)
        return prepared

    def evaluate(
        self,
        span_dict: Dict[str, Any],
        *,
        context_state: Dict[str, Any],
        policy: str = "",
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Judge all applicable span primitives in one bounded LLM call."""
        requested = metrics if metrics is not None else self.metric_names
        prompt_payload = {
            "requested_metrics": requested,
            "current_span_delta": self.prepare_span(span_dict),
            "trajectory_state_before_span": context_state,
            "policy": policy[:5000],
            "output_schema": {
                "metrics": [
                    {
                        "metric_name": "exact requested metric name",
                        "score": "integer 0 or 1",
                        "reasoning": "concise context-grounded explanation",
                    }
                ],
                "needs_more_context": "boolean; true only if additional evidence is needed",
            },
        }
        if self.options.span_context_mode == "legacy":
            prompt_payload["output_schema"].pop("needs_more_context")
            prompt_payload["output_schema"]["state_delta"] = {
                "claims": [],
                "intent_updates": [],
                "evidence_links": [],
            }
        results_by_name: Dict[str, Dict[str, Any]] = {}
        state_delta: Dict[str, Any] = {}
        needs_more_context = False
        usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        parse_error: Exception | None = None

        def collect_metrics(
            parsed: Dict[str, Any],
            expected: List[str],
        ) -> None:
            raw_metrics = parsed.get("metrics")
            if isinstance(raw_metrics, dict):
                raw_metrics = [
                    {
                        "metric_name": name,
                        **(item if isinstance(item, dict) else {}),
                    }
                    for name, item in raw_metrics.items()
                ]
            if not isinstance(raw_metrics, list):
                raw_metrics = [parsed] if parsed.get("metric_name") else []

            by_name = {
                str(item.get("metric_name") or ""): item
                for item in raw_metrics
                if isinstance(item, dict)
            }
            by_short_name = {
                name.split(".")[-1]: item for name, item in by_name.items()
            }
            by_normalized_name = {
                re.sub(r"[^a-z0-9]", "", name.split(".")[-1].casefold()): item
                for name, item in by_name.items()
            }
            for metric_name in expected:
                normalized_name = re.sub(
                    r"[^a-z0-9]",
                    "",
                    metric_name.split(".")[-1].casefold(),
                )
                item = (
                    by_name.get(metric_name)
                    or by_short_name.get(metric_name.split(".")[-1])
                    or by_normalized_name.get(normalized_name)
                )
                if item is None:
                    continue
                raw_score = item.get("score", item.get("value"))
                if isinstance(raw_score, str):
                    normalized_score = raw_score.strip().casefold()
                    if normalized_score in {"pass", "passed", "true"}:
                        raw_score = 1
                    elif normalized_score in {"fail", "failed", "false"}:
                        raw_score = 0
                try:
                    score = float(raw_score)
                except (TypeError, ValueError):
                    continue
                if score not in {0.0, 1.0}:
                    continue
                results_by_name[metric_name] = {
                    "metric_name": metric_name,
                    "value": score,
                    "reasoning": str(item.get("reasoning") or ""),
                    "success": True,
                }

        def add_usage(response: Any) -> None:
            usage = getattr(response, "usage", None)
            prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
            total_tokens = int(
                getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens)
            )
            usage_totals["prompt_tokens"] += prompt_tokens
            usage_totals["completion_tokens"] += completion_tokens
            usage_totals["total_tokens"] += total_tokens

        max_attempts = self.options.span_judge_max_attempts
        for attempt in range(max_attempts):
            missing = [
                metric_name
                for metric_name in requested
                if metric_name not in results_by_name
            ]
            attempt_payload = {
                **prompt_payload,
                "requested_metrics": missing,
            }
            messages = [
                {
                    "role": "system",
                    "content": _SPAN_STATE_DELTA_SYSTEM_PROMPT
                    + (
                        _FOCUSED_RESPONSE_INSTRUCTIONS
                        + _FOCUSED_TRANSITION_INSTRUCTIONS
                        if self.options.span_context_mode == "focused"
                        else _LEGACY_RESPONSE_INSTRUCTIONS
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        attempt_payload,
                        ensure_ascii=True,
                        default=str,
                    ),
                },
            ]
            if attempt:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "The previous response omitted or invalidated the "
                            f"remaining requested metrics: {missing}. Return strict "
                            "compact JSON for only these metrics, with one score "
                            "of 0 or 1 for each. Do not omit a metric."
                        ),
                    }
                )
            response = self._query(
                messages,
                max_tokens=min(
                    8192,
                    self.options.span_judge_max_tokens * (2**attempt),
                ),
            )
            add_usage(response)

            content = (response.choices[0].message.content or "").strip()
            try:
                parsed = self.parse_response(content)
            except (json.JSONDecodeError, ValueError) as exc:
                parse_error = exc
                continue
            candidate_delta = parsed.get("state_delta")
            needs_more_context = (
                needs_more_context or parsed.get("needs_more_context") is True
            )
            if isinstance(candidate_delta, dict) and candidate_delta:
                state_delta = candidate_delta
            collect_metrics(parsed, missing)
            if len(results_by_name) == len(requested):
                break

        remaining = [
            metric_name
            for metric_name in requested
            if metric_name not in results_by_name
        ]
        for metric_name in remaining:
            single_payload = {
                **prompt_payload,
                "requested_metrics": [metric_name],
                "output_schema": {
                    "metrics": [
                        {
                            "metric_name": metric_name,
                            "score": "integer 0 or 1",
                            "reasoning": "one concise sentence",
                        }
                    ]
                },
            }
            messages = [
                {
                    "role": "system",
                    "content": _SPAN_STATE_DELTA_SYSTEM_PROMPT
                    + (
                        ""
                        if self.options.span_context_mode == "focused"
                        else _LEGACY_RESPONSE_INSTRUCTIONS
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        single_payload,
                        ensure_ascii=True,
                        default=str,
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Return exactly one result for {metric_name}. "
                        "Use a binary numeric score of 0 or 1."
                    ),
                },
            ]
            response = self._query(
                messages,
                max_tokens=self.options.span_judge_max_tokens,
            )
            add_usage(response)
            content = (response.choices[0].message.content or "").strip()
            try:
                parsed = self.parse_response(content)
            except (json.JSONDecodeError, ValueError) as exc:
                parse_error = exc
                continue
            collect_metrics(parsed, [metric_name])

        results = [
            results_by_name[metric_name]
            for metric_name in requested
            if metric_name in results_by_name
        ]
        failed = [
            {
                "metric_name": metric_name,
                "error_message": (
                    "Combined judge omitted requested metric after "
                    f"{max_attempts} attempt(s)"
                    + (f": {parse_error}" if parse_error else "")
                ),
            }
            for metric_name in requested
            if metric_name not in results_by_name
        ]
        return {
            "span_id": span_dict.get("span_id", ""),
            "entity_type": span_dict.get("entity_type", ""),
            "entity_name": span_dict.get("entity_name", ""),
            "results": results,
            "failed_metrics": failed,
            "state_delta": state_delta,
            "needs_more_context": needs_more_context,
            "usage": usage_totals,
        }

    @staticmethod
    def parse_response(raw_text: str) -> Dict[str, Any]:
        """Parse a JSON object even when a provider prefixes brief reasoning."""
        text = (raw_text or "").strip()
        if "```json" in text:
            text = text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in text:
            text = text.split("```", 1)[1].split("```", 1)[0].strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", text):
            try:
                parsed, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
        raise json.JSONDecodeError("No JSON object found", text, 0)
