#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Temporal Metrics Processor.

Orchestrates temporal evaluation of agent sessions using three core primitives:
1. Groundedness — factual claims trace to evidence
2. IntentRecognition — requirements identified, tracked, and addressed
3. Relevancy — no contradictions, valid reasoning chains

Flow:
  1. Accept spans supplied by the caller
  2. Iterate spans sequentially, accumulating trajectory context
  3. For each span, compute all applicable primitives in one state-delta call
  4. Post-processing: one shared high-level trajectory audit
  5. Return scored result
"""

import asyncio
import json
import logging
import re
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from metrics_computation_engine.llm_judge.llm import LLMClient
from metrics_computation_engine.models.requests import LLMJudgeConfig
from stateful_evals_be.evaluation.cost_estimator import estimate_token_cost
from stateful_evals_be.evaluation.inter_step_review import run_inter_step_review
from stateful_evals_be.evaluation.span_judge import SpanJudge
from stateful_evals_be.evaluation.span_normalization import SpanNormalizer
from stateful_evals_be.evaluation.trajectory_context import (
    TrajectoryContext,
    _timestamp_ns,
)
from stateful_evals_be.models.requests import (
    EvalSummary,
    FailureDetail,
    MetricFailure,
    SamplingConfig,
    SessionResult,
    SpanMetricResult,
    TemporalMetricOptions,
    TokenUsage,
)
from stateful_evals_be.models.spans import SpanInput
from stateful_evals_be.integrations.oxp import SessionSpanClient

if TYPE_CHECKING:
    from metrics_computation_engine.llm_judge.jury import Jury
    from stateful_evals_be.models.requests import IntentState


def _empty_usage() -> Dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


logger = logging.getLogger("stateful_evals_be.processor")

CORE_METRICS = [
    "mdt.Groundedness",
    "mdt.IntentRecognition",
    "mdt.Relevancy",
]

INTENT_METRIC = "mdt.IntentRecognition"
GROUNDEDNESS_METRIC = "mdt.Groundedness"
RELEVANCY_METRIC = "mdt.Relevancy"

_INTENT_METRIC_NAMES = {"mdt.IntentRecognition", "IntentRecognition"}
_GROUNDEDNESS_METRIC_NAMES = {"mdt.Groundedness", "Groundedness"}
_RELEVANCY_METRIC_NAMES = {"mdt.Relevancy", "Relevancy"}


class TemporalMetricsProcessor:
    """Temporal evaluation processor using three core primitives.

    Flow:
      1. Accept spans from the caller (or fetch through the in-process API library)
      2. For each span: jointly compute Groundedness + IntentRecognition + Relevancy
      3. Accumulate trajectory context between spans
      4. Run deterministic prechecks and one shared final audit
      5. Return SessionResult
    """

    def __init__(
        self,
        llm_config: LLMJudgeConfig,
        options: Optional[TemporalMetricOptions] = None,
        *,
        api_client: SessionSpanClient | None = None,
    ):
        self.llm_config = deepcopy(llm_config)
        self.metric_names = list(CORE_METRICS)
        self.options = (
            deepcopy(options) if options is not None else TemporalMetricOptions()
        )
        self.api_client = api_client

        import threading

        self._thread_local = threading.local()

        self.llm_client = LLMClient(
            {
                "LLM_MODEL_NAME": llm_config.LLM_MODEL_NAME,
                "LLM_BASE_MODEL_URL": llm_config.LLM_BASE_MODEL_URL,
                "LLM_API_KEY": llm_config.LLM_API_KEY,
            }
        )

        self._warm_inprocess_metric_catalog()

        logger.info(
            f"Initialized TemporalMetricsProcessor | "
            f"metrics={self.metric_names} | mce=library"
        )

    @staticmethod
    def _warm_inprocess_metric_catalog() -> None:
        try:
            from metrics_computation_engine.util import (
                get_all_metric_classes,
                get_metric_adapters,
            )

            get_all_metric_classes()
            get_metric_adapters()
        except Exception:
            logger.exception("Failed to warm in-process metric catalog cache.")

    # ================================================================
    # Database retrieval through the in-process API library
    # ================================================================

    @staticmethod
    def _oxp_span_to_otel_format(span: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility alias for the OXP integration's normalizer."""
        from stateful_evals_be.integrations.oxp import oxp_span_to_otel

        return oxp_span_to_otel(span)

    def fetch_spans_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetch all session spans directly through the API library's LocalClient."""
        from stateful_evals_be.integrations.oxp import (
            fetch_session_spans,
            local_api_client,
        )

        if self.api_client is not None:
            return fetch_session_spans(self.api_client, session_id)
        with local_api_client() as client:
            return fetch_session_spans(client, session_id)

    def close(self) -> None:
        """Compatibility hook; database connections are scoped to retrieval.

        The processor owns no service transports. Caller-supplied API clients
        remain open; MCE model-client lifecycle is unchanged.
        """

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    # ================================================================
    # In-process MCE span metric computation
    # ================================================================

    def _get_thread_jury(self) -> "Jury":
        jury = getattr(self._thread_local, "jury", None)
        if jury is None:
            from metrics_computation_engine.llm_judge.jury import Jury

            jury = Jury(
                {
                    "LLM_MODEL_NAME": self.llm_config.LLM_MODEL_NAME,
                    "LLM_BASE_MODEL_URL": self.llm_config.LLM_BASE_MODEL_URL,
                    "LLM_API_KEY": self.llm_config.LLM_API_KEY,
                },
                num_models=1,
            )
            tls = self._thread_local
            for llm in jury.llms:
                _orig_query = llm.query

                def _capturing_query(*a, _orig=_orig_query, _tls=tls, **kw):
                    kw.setdefault("max_tokens", self.options.span_judge_max_tokens)
                    if self.options.reasoning_effort:
                        kw.setdefault("reasoning_effort", self.options.reasoning_effort)
                    resp = _orig(*a, **kw)
                    usage = getattr(resp, "usage", None)
                    if usage:
                        pt = getattr(usage, "prompt_tokens", 0) or 0
                        ct = getattr(usage, "completion_tokens", 0) or 0
                        tt = getattr(usage, "total_tokens", 0) or (pt + ct)
                        _tls.mce_pt = getattr(_tls, "mce_pt", 0) + pt
                        _tls.mce_ct = getattr(_tls, "mce_ct", 0) + ct
                        _tls.mce_tt = getattr(_tls, "mce_tt", 0) + tt
                    return resp

                llm.query = _capturing_query
            self._thread_local.jury = jury
        return jury

    def _mce_reset_thread_usage(self):
        self._thread_local.mce_pt = 0
        self._thread_local.mce_ct = 0
        self._thread_local.mce_tt = 0

    def _mce_get_thread_usage(self) -> Dict[str, int]:
        tls = self._thread_local
        return {
            "prompt_tokens": getattr(tls, "mce_pt", 0),
            "completion_tokens": getattr(tls, "mce_ct", 0),
            "total_tokens": getattr(tls, "mce_tt", 0),
        }

    def compute_span_metrics_inprocess(
        self,
        span_dict: Dict[str, Any],
        context: str = "",
        policy: str = "",
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        from metrics_computation_engine.entities.models.span import SpanEntity
        from metrics_computation_engine.util import get_metric_class

        span_data = dict(span_dict)
        span_data.setdefault("raw_span_data", {})
        span_data.setdefault("contains_error", False)
        span_data.setdefault("timestamp", "")

        span_entity = SpanEntity(**span_data)

        compute_kwargs: Dict[str, Any] = {}
        if context:
            compute_kwargs["context"] = context
        if policy:
            compute_kwargs["policy"] = policy

        metric_names = metrics if metrics is not None else self.metric_names
        results: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        self._mce_reset_thread_usage()
        jury = self._get_thread_jury()

        for metric_name in metric_names:
            try:
                metric_cls, resolved_name = get_metric_class(metric_name)
                metric_instance = metric_cls(resolved_name)
                metric_instance.jury = jury

                loop = asyncio.new_event_loop()
                try:
                    result = loop.run_until_complete(
                        metric_instance.compute(span_entity, **compute_kwargs)
                    )
                finally:
                    loop.close()

                if result is not None:
                    result_dict = asdict(result) if is_dataclass(result) else result
                    results.append(result_dict)
                else:
                    failed.append(
                        {
                            "metric_name": resolved_name,
                            "error_message": "Metric returned None",
                        }
                    )
            except Exception as e:
                logger.error(f"In-process metric error ({metric_name}): {e}")
                failed.append(
                    {
                        "metric_name": metric_name,
                        "error_message": str(e),
                    }
                )

        return {
            "span_id": span_entity.span_id,
            "entity_type": span_entity.entity_type,
            "entity_name": span_entity.entity_name,
            "results": results,
            "failed_metrics": failed,
            "usage": self._mce_get_thread_usage(),
        }

    # Compatibility aliases for callers of the former normalization helpers.
    _normalize_text = staticmethod(SpanNormalizer._normalize_text)
    _infer_message_role = staticmethod(SpanNormalizer._infer_message_role)
    _extract_message_entry = staticmethod(SpanNormalizer._extract_message_entry)
    _iter_message_lists = staticmethod(SpanNormalizer._iter_message_lists)
    _find_text_by_keys = staticmethod(SpanNormalizer._find_text_by_keys)
    _iter_entity_payloads = staticmethod(SpanNormalizer._iter_entity_payloads)
    _first_span_attribute = staticmethod(SpanNormalizer._first_span_attribute)
    _span_kind = staticmethod(SpanNormalizer._span_kind)
    _entity_input = staticmethod(SpanNormalizer._entity_input)
    _entity_output = staticmethod(SpanNormalizer._entity_output)
    _entity_name = staticmethod(SpanNormalizer._entity_name)
    _find_scalar_text_by_keys = staticmethod(SpanNormalizer._find_scalar_text_by_keys)
    _extract_user_request_history_from_raw_spans = staticmethod(
        SpanNormalizer.extract_user_request_history
    )
    _payload_has_meaningful_text = staticmethod(
        SpanNormalizer._payload_has_meaningful_text
    )
    _load_json_payload = staticmethod(SpanNormalizer._load_json_payload)
    _extract_parent_llm_payloads = staticmethod(
        SpanNormalizer._extract_parent_llm_payloads
    )
    _otel_trace_to_span_dict = staticmethod(SpanNormalizer.normalize_span)
    _extract_coordination_context = staticmethod(
        SpanNormalizer.extract_coordination_context
    )
    _extract_system_message = staticmethod(SpanNormalizer.extract_system_message)
    _extract_agent_semantic_contracts = staticmethod(
        SpanNormalizer.extract_agent_semantic_contracts
    )
    _extract_tool_definitions = staticmethod(SpanNormalizer.extract_tool_definitions)
    _is_effectively_empty_payload = staticmethod(
        SpanNormalizer._is_effectively_empty_payload
    )
    _agent_span_has_routing_or_answer = staticmethod(
        SpanNormalizer._agent_span_has_routing_or_answer
    )
    _deduplicate_spans = staticmethod(SpanNormalizer.deduplicate_spans)
    _extract_full_tool_outputs = staticmethod(SpanNormalizer.extract_tool_outputs)
    _extract_final_answer_from_raw_spans = staticmethod(
        SpanNormalizer.extract_final_answer
    )
    _compact_json_value = staticmethod(SpanJudge.compact_value)
    _parse_json_response = staticmethod(SpanJudge.parse_response)

    def _create_span_judge(self) -> SpanJudge:
        return SpanJudge(
            query=self._query_with_budget,
            options=self.options,
            metric_names=self.metric_names,
        )

    def _compact_span_delta(self, span_dict: Dict[str, Any]) -> Dict[str, Any]:
        return self._create_span_judge().prepare_span(span_dict)

    def compute_span_state_delta(
        self,
        span_dict: Dict[str, Any],
        *,
        context_state: Dict[str, Any],
        policy: str = "",
        metrics: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._create_span_judge().evaluate(
            span_dict, context_state=context_state, policy=policy, metrics=metrics
        )

    def _query_with_budget(
        self,
        messages: List[Dict[str, Any]],
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> Any:
        model_name = str(
            getattr(getattr(self, "llm_config", None), "LLM_MODEL_NAME", "")
        )
        if "claude-sonnet" in model_name.casefold():
            temperature = 1.0
        kwargs: Dict[str, Any] = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        reasoning_effort = getattr(
            getattr(self, "options", None),
            "reasoning_effort",
            "low",
        )
        if reasoning_effort:
            kwargs["reasoning_effort"] = reasoning_effort
        try:
            return self.llm_client.query(messages, **kwargs)
        except TypeError as exc:
            # Lightweight test/custom clients may expose the older minimal
            # signature. A Python argument error happens before a network call.
            if "unexpected keyword argument" not in str(exc):
                raise
            return self.llm_client.query(messages, temperature=temperature)

    # ================================================================
    # Context synchronization
    # ================================================================

    @staticmethod
    def _sort_spans_chronologically(
        raw_spans: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Sort by parsed start time; fall back to the historical string order."""
        stamps = [_timestamp_ns(span.get("Timestamp")) for span in raw_spans]
        if raw_spans and all(stamp is not None for stamp in stamps):
            order = sorted(range(len(raw_spans)), key=lambda index: stamps[index])
            return [raw_spans[index] for index in order]
        return sorted(raw_spans, key=lambda span: str(span.get("Timestamp", "")))

    @staticmethod
    def _declared_roster(
        raw_spans: List[Dict[str, Any]],
        spans_by_id: Dict[str, Dict[str, Any]],
    ) -> List[tuple[str, int]]:
        """Scan agent identities (names only) before any span is ingested.

        Explicit agent attributes define the roster. When a trace runs one
        service per agent and has no agent attributes, those services are the
        roster. A single-service trace with no agent attributes has no
        roster, which keeps the historical single-agent behavior.

        An identity counts as an agent only if at least one of its spans is an
        LLM call or a tool call; framework nodes that merely carry an agent
        attribute (for example a finalize node) are left out.
        """
        explicit: Dict[str, int] = {}
        services: Dict[str, int] = {}
        working: set[str] = set()
        for index, span in enumerate(raw_spans):
            agent_id = SpanNormalizer.resolve_agent_id(span, spans_by_id)
            service = str(span.get("ServiceName") or "").strip()
            if agent_id:
                explicit.setdefault(agent_id, index)
            if service:
                services.setdefault(service, index)
            if SpanNormalizer.entity_type(span) in {"llm", "tool"}:
                working.update(item for item in (agent_id, service) if item)
        roster = {agent: index for agent, index in explicit.items() if agent in working}
        if not roster and len(services) > 1:
            for service, index in services.items():
                if service in working:
                    roster[service] = index
        return sorted(roster.items(), key=lambda item: item[1])

    def _synchronize_final_answer(
        self,
        traj_ctx: TrajectoryContext,
        raw_spans: List[Dict[str, Any]],
    ) -> None:
        """Record one canonical final answer while honoring adapter provenance."""
        raw_answer, raw_index = self._extract_final_answer_from_raw_spans(raw_spans)
        coordination = traj_ctx.coordination_context
        final_answer = coordination.final_response or raw_answer
        final_index = raw_index
        if coordination.final_response and not (
            raw_answer and _same_answer_text(raw_answer, coordination.final_response)
        ):
            # The adapter's final_response_event_index is an adapter-native
            # coordinate; never store it as a span index. Locate the span that
            # emitted the text instead.
            located = traj_ctx.span_index_for_text(coordination.final_response)
            final_index = located if located >= 0 else raw_index
        if not 0 <= final_index < len(raw_spans):
            located = traj_ctx.span_index_for_text(final_answer)
            final_index = located if located >= 0 else len(raw_spans) - 1
        if final_answer and final_answer.strip():
            traj_ctx.set_final_answer(
                final_answer,
                final_index,
                record_synthesis=True,
            )

    @classmethod
    def _ingest_agent_semantic_contracts(
        cls,
        context: TrajectoryContext,
        raw_spans: List[Dict[str, Any]],
        root_request: str = "",
    ) -> None:
        for agent_id, content, span_index in cls._extract_agent_semantic_contracts(
            raw_spans,
            root_request,
        ):
            context.add_policy_rule(
                content,
                source_name=f"semantic_contract:{agent_id}",
                span_index=span_index,
            )

    # ================================================================
    # Metric selection
    # ================================================================

    def _metrics_for_span(self, span_dict: Dict[str, Any]) -> List[str]:
        entity_type = span_dict.get("entity_type", "")

        # Framework wrapper spans still feed the trajectory context, but metrics
        # belong on the LLM and application tool spans they wrap.
        if SpanNormalizer.is_framework_span(span_dict.get("attributes") or {}):
            return []

        if entity_type == "tool":
            return [INTENT_METRIC, RELEVANCY_METRIC]

        if entity_type == "llm":
            input_empty = self._is_effectively_empty_payload(
                span_dict.get("input_payload")
            )
            output_empty = self._is_effectively_empty_payload(
                span_dict.get("output_payload")
            )
            if input_empty and output_empty:
                return []
            if output_empty:
                return [RELEVANCY_METRIC]
            return [GROUNDEDNESS_METRIC, INTENT_METRIC, RELEVANCY_METRIC]

        return []

    @staticmethod
    def _is_intent_metric(metric_name: str) -> bool:
        return metric_name in _INTENT_METRIC_NAMES

    # ================================================================
    # Intent state resolution
    # ================================================================

    _POLICY_REJECTION_SIGNALS = re.compile(
        r"(policy\s+(prohibit|reject|refus|den|restrict|forbid|disallow|prevent|block))"
        r"|(reject(?:ed|ing|s)?\s+(?:per|due\s+to|because\s+of|by)\s+policy)"
        r"|(per\s+policy\b.{0,40}(?:cannot|denied|refused|rejected))"
        r"|(correctly\s+(?:denied|rejected|refused|declined))"
        r"|(not\s+permitted\s+by\s+policy)"
        r"|(compliance.{0,20}(?:reject|refus|den))",
        re.IGNORECASE,
    )

    @staticmethod
    def _has_policy_rejection_signal(reasoning: str) -> bool:
        return bool(
            TemporalMetricsProcessor._POLICY_REJECTION_SIGNALS.search(reasoning or "")
        )

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "yes", "1", "pass", "passed"}:
                return True
            if normalized in {"false", "no", "0", "fail", "failed"}:
                return False
        return default

    @staticmethod
    def _resolve_intent_states(
        intent_events: List[Dict[str, Any]],
        total_spans: int,
    ) -> List["IntentState"]:
        from stateful_evals_be.models.requests import IntentEvent, IntentState

        if not intent_events:
            return []

        tool_events = [
            e
            for e in intent_events
            if e.get("span_type") == "tool"
            and not TemporalMetricsProcessor._is_effectively_empty_payload(
                e.get("output_payload")
            )
        ]
        llm_events = sorted(
            [e for e in intent_events if e.get("span_type") == "llm"],
            key=lambda e: e.get("span_index", 0),
        )

        intents_by_name: Dict[str, List[Dict[str, Any]]] = {}
        for event in tool_events:
            name = event.get("entity_name", "unknown")
            intents_by_name.setdefault(name, []).append(event)

        for event in llm_events:
            name = event.get("entity_name", "unknown")
            if name not in intents_by_name:
                intents_by_name.setdefault(name, []).append(event)

        states: List[IntentState] = []
        for name, events in intents_by_name.items():
            events.sort(key=lambda e: e.get("span_index", 0))
            first_span = events[0].get("span_index", 0)
            last_span = events[-1].get("span_index", 0)

            timeline = [
                IntentEvent(
                    span_index=e.get("span_index", 0),
                    span_type=e.get("span_type", ""),
                    entity_name=e.get("entity_name", ""),
                    score=float(e.get("score", 0)),
                    reasoning=e.get("reasoning", ""),
                )
                for e in events
            ]

            best_score = max(float(e.get("score", 0)) for e in events)

            has_policy_rejection = any(
                TemporalMetricsProcessor._has_policy_rejection_signal(
                    e.get("reasoning", "")
                )
                for e in events
            )

            if best_score >= 1.0 and has_policy_rejection:
                state = "rejected_per_policy"
            elif best_score >= 1.0:
                state = "fulfilled"
            elif has_policy_rejection:
                state = "rejected_per_policy"
            elif len(events) == 1 and first_span < total_spans * 0.4:
                state = "dormant"
            elif best_score == 0.0 and first_span >= total_spans * 0.8:
                state = "dormant"
            else:
                state = "drifting"

            states.append(
                IntentState(
                    name=name,
                    state=state,
                    first_span=first_span,
                    last_span=last_span,
                    occurrences=len(events),
                    final_score=best_score,
                    timeline=timeline,
                )
            )

        state_order = {
            "failed": 0,
            "drifting": 1,
            "fulfilled": 2,
            "rejected_per_policy": 3,
            "dormant": 4,
        }
        states.sort(key=lambda s: state_order.get(s.state, 5))
        return states

    _RESOLVED_INTENT_STATES = {"fulfilled", "rejected_per_policy", "dormant"}

    @staticmethod
    def _count_unsatisfied_intents(intent_states: List[Any]) -> int:
        return sum(
            1
            for state in intent_states
            if getattr(state, "state", "")
            not in TemporalMetricsProcessor._RESOLVED_INTENT_STATES
            and int(getattr(state, "occurrences", 0) or 0) >= 2
            and float(getattr(state, "final_score", 0)) == 0.0
        )

    @staticmethod
    def _build_intent_aftermath(intent_states: List[Any]) -> str:
        if not intent_states:
            return "No tracked intents."

        fulfilled = [s for s in intent_states if getattr(s, "state", "") == "fulfilled"]
        rejected = [
            s for s in intent_states if getattr(s, "state", "") == "rejected_per_policy"
        ]
        drifting = [s for s in intent_states if getattr(s, "state", "") == "drifting"]
        dormant = [s for s in intent_states if getattr(s, "state", "") == "dormant"]
        failed = [s for s in intent_states if getattr(s, "state", "") == "failed"]

        parts = [
            f"Intent resolution at trajectory end: "
            f"{len(fulfilled)} fulfilled, {len(rejected)} rejected per policy, "
            f"{len(drifting)} drifting, {len(dormant)} dormant, {len(failed)} failed "
            f"(out of {len(intent_states)} total tracked intents).",
        ]
        if fulfilled:
            names = [getattr(s, "name", "?") for s in fulfilled]
            parts.append(f"Fulfilled intents: {', '.join(names)}.")
        if rejected:
            names = [getattr(s, "name", "?") for s in rejected]
            parts.append(
                f"Rejected per policy (agent correctly denied): {', '.join(names)}."
            )
        if drifting:
            names = [getattr(s, "name", "?") for s in drifting]
            parts.append(f"Drifting intents: {', '.join(names)}.")

        if len(fulfilled) == len(intent_states):
            parts.append(
                "ALL tracked tool intents reached fulfilled state. "
                "Failures that are purely procedural or intermediate "
                "missteps that did not prevent intent fulfillment "
                "should be classified as MINOR, not FATAL."
            )
        return " ".join(parts)

    # ================================================================
    # Post-loop: cross-span validation & trajectory pattern detection
    # ================================================================

    _MIN_FINAL_ANSWER_LEN = 40

    def _cross_validate_final_answer(
        self,
        traj_ctx: TrajectoryContext,
        system_message: str,
        session_id: str,
        raw_spans: Optional[List[Dict[str, Any]]] = None,
    ) -> List[MetricFailure]:
        from stateful_evals_be.prompts.cross_span_validation import (
            CROSS_SPAN_VALIDATION_SYSTEM_PROMPT,
            CROSS_SPAN_VALIDATION_USER_PROMPT,
        )

        ctx = traj_ctx.get_final_answer_context()
        final_answer = ctx["final_answer"]
        span_index = ctx["final_answer_span_index"]

        if (
            not final_answer or len(final_answer.strip()) < self._MIN_FINAL_ANSWER_LEN
        ) and raw_spans:
            final_answer, span_index = self._extract_final_answer_from_raw_spans(
                raw_spans
            )

        if not final_answer or len(final_answer.strip()) < self._MIN_FINAL_ANSWER_LEN:
            logger.info(
                f"[{session_id}] Cross-span validation skipped: final answer too short or empty"
            )
            return []

        tool_output_text = (
            self._extract_full_tool_outputs(raw_spans) if raw_spans else ""
        )
        if not tool_output_text:
            tool_outputs = ctx["all_tool_outputs"]
            if not tool_outputs:
                logger.info(
                    f"[{session_id}] Cross-span validation skipped: no tool outputs in evidence"
                )
                return []
            tool_output_text = "\n\n".join(
                f"[Step {f.span_index + 1}, {f.source_name}]\n{f.content}"
                for f in tool_outputs
            )

        user_question = ctx["user_question"] or "(not captured)"
        if raw_spans:
            raw_user_question = self._extract_user_request_history_from_raw_spans(
                raw_spans
            )
            if raw_user_question:
                user_question = raw_user_question
        policy = system_message[:3000] if system_message else "No policy provided."

        user_prompt = CROSS_SPAN_VALIDATION_USER_PROMPT.format(
            user_question=user_question,
            final_answer=final_answer[:4000],
            tool_outputs=tool_output_text[:20000],
            policy=policy,
        )

        messages = [
            {"role": "system", "content": CROSS_SPAN_VALIDATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._query_with_budget(
                messages,
                max_tokens=getattr(
                    getattr(self, "options", None),
                    "final_judge_max_tokens",
                    4096,
                ),
            )
            result_text = (response.choices[0].message.content or "").strip()

            usage = getattr(response, "usage", None)
            cs_pt = cs_ct = cs_tt = 0
            if usage:
                cs_pt = getattr(usage, "prompt_tokens", 0) or 0
                cs_ct = getattr(usage, "completion_tokens", 0) or 0
                cs_tt = getattr(usage, "total_tokens", 0) or (cs_pt + cs_ct)
            self._last_cross_span_usage = {
                "prompt_tokens": cs_pt,
                "completion_tokens": cs_ct,
                "total_tokens": cs_tt,
            }

            if not result_text:
                return []

            parsed = self._parse_json_response(result_text)
        except Exception as exc:
            logger.warning(f"[{session_id}] Cross-span validation failed: {exc}")
            return []

        failures_out: List[MetricFailure] = []

        hard_violations = parsed.get("hard_rule_violations", [])
        for violation in hard_violations:
            sev = float(violation.get("severity", 1.0))
            if sev < 0.9:
                continue
            vtype = violation.get("violation_type", "unknown")
            content = violation.get("content", "")[:300]
            explanation = violation.get("explanation", "")[:300]
            reasoning = f"Hard-rule violation ({vtype}): {content} — {explanation}"
            failures_out.append(
                MetricFailure(
                    metric_name="HardRuleViolation",
                    score=0.0,
                    reasoning=reasoning,
                    span_index=span_index,
                    span_type="llm",
                    input_payload=None,
                    output_payload=final_answer[:1000],
                    eval_context="cross_span_hard_rule",
                    entity_name="final_answer",
                    policy=system_message,
                )
            )

        if parsed.get("is_grounded", True) and not failures_out:
            return []

        ungrounded = parsed.get("ungrounded_claims", [])
        high_severity = [
            c
            for c in ungrounded
            if float(c.get("severity", 0)) >= 0.9
            and c.get("issue") in ("fabricated", "contradicted")
        ]

        if high_severity:
            worst = max(high_severity, key=lambda c: float(c.get("severity", 0)))
            explanation = worst.get("evidence_gap", worst.get("explanation", ""))
            reasoning = (
                f"Cross-span validation ({worst.get('issue', 'fabricated')}): "
                f"{worst.get('claim', '')[:200]} — {explanation[:300]}"
            )

            failures_out.append(
                MetricFailure(
                    metric_name="Groundedness",
                    score=0.0,
                    reasoning=reasoning,
                    span_index=span_index,
                    span_type="llm",
                    input_payload=None,
                    output_payload=final_answer[:1000],
                    eval_context="cross_span_validation",
                    entity_name="final_answer",
                    policy=system_message,
                )
            )

        return failures_out

    def _review_final_outcome(
        self,
        traj_ctx: TrajectoryContext,
        system_message: str,
        session_id: str,
        intent_states: List[Any],
        raw_spans: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple[List[FailureDetail], List[FailureDetail]]:
        """Judge whether the final answer/action resolves the request under policy."""
        from stateful_evals_be.prompts.final_outcome_review import (
            FINAL_OUTCOME_REVIEW_SYSTEM_PROMPT,
            FINAL_OUTCOME_REVIEW_USER_PROMPT,
        )

        self._last_final_outcome_usage = _empty_usage()

        if raw_spans:
            self._synchronize_final_answer(traj_ctx, raw_spans)
        ctx = traj_ctx.get_final_answer_context()
        final_answer = ctx["final_answer"]
        span_index = ctx["final_answer_span_index"]

        if not final_answer or not final_answer.strip():
            detail = FailureDetail(
                metric="FinalOutcomeRelevancy",
                metric_score=0.0,
                fatality_score=1.0,
                reasoning="No final user-facing answer or action was found.",
                explanation=(
                    "Final outcome review: the trajectory did not produce a "
                    "detectable final response that resolves the user's request "
                    "under policy."
                ),
                span_index=max(span_index, 0),
                span_type="llm",
                entity_name="final_answer",
                observed_impact="incomplete_resolution",
                confidence=0.8,
            )
            return [detail], []

        tool_output_text = (
            self._extract_full_tool_outputs(raw_spans) if raw_spans else ""
        )
        if not tool_output_text:
            tool_outputs = ctx["all_tool_outputs"]
            tool_output_text = "\n\n".join(
                f"[Step {f.span_index + 1}, {f.source_name}]\n{f.content}"
                for f in tool_outputs
            )

        user_question = ctx["user_question"] or "(not captured)"
        if raw_spans:
            raw_user_question = self._extract_user_request_history_from_raw_spans(
                raw_spans
            )
            if raw_user_question:
                user_question = raw_user_question
        aftermath = self._build_intent_aftermath(intent_states)
        trajectory_summary = traj_ctx.get_full_summary()

        user_prompt = FINAL_OUTCOME_REVIEW_USER_PROMPT.format(
            user_question=user_question[:2000],
            final_answer=final_answer[:5000],
            policy=(system_message or "No policy provided.")[:5000],
            aftermath=aftermath[:3000],
            trajectory_summary=trajectory_summary[:5000],
            tool_outputs=(tool_output_text or "No tool outputs captured.")[:20000],
        )

        messages = [
            {"role": "system", "content": FINAL_OUTCOME_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self._query_with_budget(
                messages,
                max_tokens=getattr(
                    getattr(self, "options", None),
                    "final_judge_max_tokens",
                    4096,
                ),
            )
            result_text = (response.choices[0].message.content or "").strip()

            usage = getattr(response, "usage", None)
            fo_pt = fo_ct = fo_tt = 0
            if usage:
                fo_pt = getattr(usage, "prompt_tokens", 0) or 0
                fo_ct = getattr(usage, "completion_tokens", 0) or 0
                fo_tt = getattr(usage, "total_tokens", 0) or (fo_pt + fo_ct)
            self._last_final_outcome_usage = {
                "prompt_tokens": fo_pt,
                "completion_tokens": fo_ct,
                "total_tokens": fo_tt,
            }

            if not result_text:
                logger.warning(f"[{session_id}] Final outcome review returned empty")
                return [], []

            parsed = self._parse_json_response(result_text)
        except Exception as exc:
            logger.warning(f"[{session_id}] Final outcome review failed: {exc}")
            return [], []

        verdict = str(parsed.get("verdict", "")).strip().upper()
        passes = self._coerce_bool(parsed.get("passes"), default=(verdict == "PASS"))
        if passes and verdict != "FAIL":
            return [], []

        try:
            severity = float(parsed.get("severity", 1.0))
        except (TypeError, ValueError):
            severity = 1.0
        severity = max(0.0, min(1.0, severity))

        is_hard_rule = self._coerce_bool(parsed.get("hard_rule_violation"))
        metric_name = str(parsed.get("failure_metric") or "FinalOutcomeRelevancy")
        observed_impact = str(parsed.get("observed_impact") or "unsupported_resolution")
        reasoning = str(
            parsed.get("reasoning")
            or "Final answer/action did not resolve the request under policy."
        )
        explanation = str(
            parsed.get("explanation")
            or "Final outcome review judged the end-to-end resolution as failing."
        )

        detail = FailureDetail(
            metric=metric_name,
            metric_score=0.0,
            fatality_score=severity,
            reasoning=reasoning,
            explanation=explanation,
            span_index=max(span_index, 0),
            span_type="llm",
            entity_name="final_answer",
            observed_impact=observed_impact,
            confidence=severity,
            policy_compliant=self._coerce_bool(
                parsed.get("policy_compliant_resolution")
            ),
            hard_rule_violation=is_hard_rule,
        )

        if is_hard_rule or severity >= 0.5:
            return [detail], []
        return [], [detail]

    @staticmethod
    def _detect_loop_pattern(
        traj_ctx: TrajectoryContext,
        threshold: int = 3,
    ) -> Optional[MetricFailure]:
        from difflib import SequenceMatcher

        claims = traj_ctx.claims
        if len(claims) < threshold:
            return None

        best_run = 1
        run_start = 0
        current_run = 1

        for i in range(1, len(claims)):
            prev = claims[i - 1].content.strip()
            curr = claims[i].content.strip()

            if not prev or not curr:
                current_run = 1
                run_start = i
                continue

            ratio = SequenceMatcher(None, prev, curr).ratio()
            if ratio > 0.85:
                current_run += 1
                if current_run > best_run:
                    best_run = current_run
            else:
                current_run = 1
                run_start = i

        if best_run < threshold:
            return None

        last_claim = (
            claims[run_start + best_run - 1]
            if run_start + best_run - 1 < len(claims)
            else claims[-1]
        )

        return MetricFailure(
            metric_name="Relevancy",
            score=0.0,
            reasoning=(
                f"Loop entrapment: agent produced {best_run} near-identical "
                f"consecutive outputs (similarity > 85%). "
                f"Content: {last_claim.content[:200]}"
            ),
            span_index=last_claim.span_index,
            span_type="llm",
            input_payload=None,
            output_payload=last_claim.content[:500],
            eval_context="loop_detection",
            entity_name=last_claim.entity_name,
        )

    @staticmethod
    def _build_trajectory_metric_supplemental(
        *,
        failures: List[MetricFailure],
        intent_states: List[Any],
        unsatisfied_intents: int,
    ) -> Dict[str, Any]:
        """Build shared state signals for trajectory-level metric judges."""
        primitive_signals = [
            {
                "metric": failure.metric_name,
                "span_index": failure.span_index,
                "span_type": failure.span_type,
                "entity_name": failure.entity_name,
                "reasoning": failure.reasoning[:600],
                "signal_type": (
                    failure.eval_context
                    if failure.eval_context
                    in {
                        "loop_detection",
                        "cross_span_validation",
                        "cross_span_hard_rule",
                    }
                    else "span_primitive"
                ),
            }
            for failure in failures[:30]
        ]
        intent_signals = [
            {
                "name": getattr(state, "name", ""),
                "state": getattr(state, "state", ""),
                "first_span": getattr(state, "first_span", 0),
                "last_span": getattr(state, "last_span", 0),
                "occurrences": getattr(state, "occurrences", 0),
                "final_score": getattr(state, "final_score", 0.0),
            }
            for state in intent_states
        ]
        return {
            "primitive_failures": primitive_signals,
            "resolved_intent_states": intent_signals,
            "unsatisfied_intents": unsatisfied_intents,
        }

    def _run_unified_final_audit(
        self,
        *,
        traj_ctx: TrajectoryContext,
        failures: List[MetricFailure],
        intent_states: List[Any],
        unsatisfied_intents: int,
        raw_spans: List[Dict[str, Any]],
        session_id: str,
    ) -> tuple[
        List[FailureDetail],
        List[FailureDetail],
        List[str],
        List[Dict[str, Any]],
        Dict[str, int],
    ]:
        """Replace three overlapping final reviews with one shared metric audit."""
        from stateful_evals_be.evaluation.trajectory_context_metrics import (
            CorrectnessMetric,
            PAPER_METRIC_SUITE,
            build_metric_suite,
            evaluate_metric_suite_batched,
        )
        from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
            LLMMetricJudge,
        )

        self._synchronize_final_answer(traj_ctx, raw_spans)

        supplemental = self._build_trajectory_metric_supplemental(
            failures=failures,
            intent_states=intent_states,
            unsatisfied_intents=unsatisfied_intents,
        )

        judge = LLMMetricJudge(
            llm_client=self.llm_client,
            model_name=self.llm_config.LLM_MODEL_NAME,
            max_tokens=self.options.final_judge_max_tokens,
            reasoning_effort=self.options.reasoning_effort,
        )
        metric_suite = self.options.high_level_metric_suite
        all_metrics = build_metric_suite(metric_suite, judge=judge)
        audit_metrics = tuple(
            metric
            for metric in all_metrics
            if not isinstance(metric, CorrectnessMetric)
        )
        audit_results = evaluate_metric_suite_batched(
            traj_ctx,
            metric_suite=metric_suite,
            stateful_result={
                "trajectory_score": None,
                "fatal_failures": [],
                "minor_failures": [],
            },
            metrics=audit_metrics,
            judge=judge,
            supplemental_context=supplemental,
        )
        if len(audit_results) != len(audit_metrics):
            raise RuntimeError(
                f"Metric suite {metric_suite!r} returned an unexpected metric count"
            )

        fatal_details: List[FailureDetail] = []
        minor_details: List[FailureDetail] = []
        patterns: List[str] = []
        failed_metric_names: set[str] = set()

        def convert(
            high_failure: Any,
            *,
            default_metric: str,
            affects_trajectory_score: bool,
        ) -> FailureDetail:
            confidence = max(0.0, min(1.0, float(high_failure.confidence)))
            return FailureDetail(
                metric=default_metric,
                metric_score=0.0,
                fatality_score=confidence,
                reasoning=high_failure.reasoning,
                explanation=high_failure.explanation,
                span_index=high_failure.span_index,
                span_type="trajectory",
                entity_name=high_failure.entity_name,
                observed_impact=high_failure.observed_impact or "metric_failure",
                confidence=confidence,
                affects_trajectory_score=affects_trajectory_score,
            )

        for result in audit_results:
            affects_trajectory_score = bool(
                result.metadata.get("affects_trajectory_score", True)
            )
            infrastructure_error = any(
                failure.observed_impact == "llm_judge_error"
                for failure in result.fatal_failures
            )
            if result.score == 0 and not infrastructure_error:
                failed_metric_names.add(result.high_level_metric)
            for high_failure in result.fatal_failures:
                detail = convert(
                    high_failure,
                    default_metric=result.high_level_metric,
                    affects_trajectory_score=affects_trajectory_score,
                )
                if high_failure.observed_impact == "llm_judge_error":
                    detail.fatality_score = 0.0
                    detail.confidence = 0.0
                    minor_details.append(detail)
                else:
                    fatal_details.append(detail)
            for high_failure in result.minor_failures:
                minor_details.append(
                    convert(
                        high_failure,
                        default_metric=result.high_level_metric,
                        affects_trajectory_score=False,
                    )
                )
            if (
                result.score == 0
                and not result.fatal_failures
                and not infrastructure_error
            ):
                minor_details.append(
                    FailureDetail(
                        metric=result.high_level_metric,
                        metric_score=0.0,
                        fatality_score=0.0,
                        reasoning=(
                            "Ignored invalid metric verdict: score 0 had no fatal finding."
                        ),
                        explanation=(
                            result.reasoning
                            or "The shared final audit returned no supporting failure."
                        ),
                        span_type="trajectory",
                        entity_name="final_answer",
                        observed_impact="invalid_metric_verdict",
                        confidence=0.0,
                    )
                )

        primitive_to_high_level = (
            {
                "groundedness": {"Groundedness"},
                "intentrecognition": {
                    "Task Completion",
                    "Instruction Following",
                    "Context Preservation",
                },
                "relevancy": {
                    "Goal Alignment",
                    "Semantic Consistency",
                    "Verification Quality",
                    "Constraint Satisfaction",
                },
            }
            if metric_suite == PAPER_METRIC_SUITE
            else {
                "groundedness": {"Hallucination", "Role Adherence"},
                "intentrecognition": {
                    "Task Completeness",
                    "Context Preservation",
                },
                "relevancy": {
                    "Task Completeness",
                    "Component Conflict",
                    "Orchestration Verification",
                },
            }
        )
        for failure in failures:
            short_name = failure.metric_name.split(".")[-1].casefold()
            if failed_metric_names & primitive_to_high_level.get(short_name, set()):
                continue
            minor_details.append(
                FailureDetail(
                    metric=failure.metric_name,
                    metric_score=failure.score,
                    fatality_score=0.3,
                    reasoning=failure.reasoning,
                    explanation=(
                        "Span-level signal retained as minor because the unified "
                        "trajectory audit found no corresponding fatal outcome."
                    ),
                    span_index=failure.span_index,
                    span_id=failure.span_id or "",
                    span_type=failure.span_type,
                    entity_name=failure.entity_name or "",
                    observed_impact="intermediate_metric_failure",
                    confidence=0.5,
                )
            )
            if failure.eval_context == "loop_detection":
                patterns.append("loop_entrapment")

        if (
            metric_suite != PAPER_METRIC_SUITE
            and unsatisfied_intents > 0
            and "Task Completeness" not in failed_metric_names
        ):
            fatal_details.append(
                FailureDetail(
                    metric="Task Completeness",
                    metric_score=0.0,
                    fatality_score=1.0,
                    reasoning=(
                        f"{unsatisfied_intents} intent(s) remained unresolved at the "
                        "end of the trajectory."
                    ),
                    explanation="Deterministic unresolved-intent trajectory check.",
                    span_type="trajectory",
                    entity_name="intent_register",
                    observed_impact="incomplete_resolution",
                    confidence=1.0,
                    affects_trajectory_score=True,
                )
            )

        payloads = [result.to_payload() for result in audit_results]
        usage = _empty_usage()
        for payload in payloads:
            metric_usage = (payload.get("metadata") or {}).get("usage") or {}
            usage["prompt_tokens"] += int(metric_usage.get("prompt_tokens", 0) or 0)
            usage["completion_tokens"] += int(
                metric_usage.get("completion_tokens", 0) or 0
            )
            usage["total_tokens"] += int(metric_usage.get("total_tokens", 0) or 0)
        logger.info(
            f"[{session_id}] Unified final audit: metrics={len(payloads)} | "
            f"fatal={len(fatal_details)} | minor={len(minor_details)} | "
            f"tokens={usage['total_tokens']}"
        )
        return fatal_details, minor_details, patterns, payloads, usage

    def _run_configured_trajectory_metrics(
        self,
        *,
        traj_ctx: TrajectoryContext,
        failures: List[MetricFailure],
        intent_states: List[Any],
        unsatisfied_intents: int,
        raw_spans: List[Dict[str, Any]],
        fatal_failures: List[FailureDetail],
        minor_failures: List[FailureDetail],
        trajectory_score: Optional[int],
        trajectory_reasoning: Optional[str],
        session_id: str,
    ) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
        """Evaluate opt-in metrics without mutating correctness state."""
        from stateful_evals_be.evaluation.trajectory_context_metrics import (
            evaluate_trajectory_metrics_batched,
        )
        from stateful_evals_be.evaluation.trajectory_context_metrics.judge import (
            LLMMetricJudge,
        )

        selectors = self.options.trajectory_metrics
        if not selectors:
            return [], _empty_usage()

        self._synchronize_final_answer(traj_ctx, raw_spans)

        supplemental = self._build_trajectory_metric_supplemental(
            failures=failures,
            intent_states=intent_states,
            unsatisfied_intents=unsatisfied_intents,
        )
        judge = LLMMetricJudge(
            llm_client=self.llm_client,
            model_name=self.llm_config.LLM_MODEL_NAME,
            max_tokens=self.options.final_judge_max_tokens,
            reasoning_effort=self.options.reasoning_effort,
        )
        results = evaluate_trajectory_metrics_batched(
            traj_ctx,
            selectors,
            stateful_result={
                "trajectory_score": trajectory_score,
                "trajectory_reasoning": trajectory_reasoning,
                "fatal_failures": [failure.model_dump() for failure in fatal_failures],
                "minor_failures": [failure.model_dump() for failure in minor_failures],
            },
            judge=judge,
            supplemental_context=supplemental,
        )
        payloads = [result.to_payload() for result in results]
        usage = _empty_usage()
        for payload in payloads:
            metric_usage = (payload.get("metadata") or {}).get("usage") or {}
            usage["prompt_tokens"] += int(metric_usage.get("prompt_tokens", 0) or 0)
            usage["completion_tokens"] += int(
                metric_usage.get("completion_tokens", 0) or 0
            )
            usage["total_tokens"] += int(metric_usage.get("total_tokens", 0) or 0)

        logger.info(
            f"[{session_id}] Configured trajectory metrics: "
            f"metrics={len(payloads)} | tokens={usage['total_tokens']}"
        )
        return payloads, usage

    # ================================================================
    # Adaptive span sampling helpers
    # ================================================================

    def _build_sampling_plan(
        self,
        raw_spans: List[Dict],
        spans_by_id: Dict,
        sampling: SamplingConfig,
    ):
        """Pre-scan spans (zero MCE calls) to compute anchors and evaluable position map.

        Returns:
            anchors (set[int]): span indices always evaluated regardless of zone rate.
            eval_pos_map (dict[int, int]): {span_index → 0-based position among evaluable spans}.
        """

        evaluable_indices: List[int] = []
        error_indices: List[int] = []
        post_large_tool_candidates: List[int] = []
        last_tool_was_large = False

        for n, raw_span in enumerate(raw_spans):
            span_dict = self._otel_trace_to_span_dict(raw_span, spans_by_id=spans_by_id)
            entity_type = span_dict["entity_type"]

            if entity_type not in ("tool", "llm"):
                last_tool_was_large = False
                continue

            if not self._metrics_for_span(span_dict):
                last_tool_was_large = False
                continue

            evaluable_indices.append(n)

            if span_dict.get("contains_error"):
                error_indices.append(n)

            if entity_type == "tool":
                output_len = len(str(span_dict.get("output_payload", "")))
                last_tool_was_large = output_len >= sampling.large_tool_output_chars
            elif entity_type == "llm":
                if last_tool_was_large:
                    post_large_tool_candidates.append(n)
                last_tool_was_large = False

        anchors: set = set()

        if evaluable_indices:
            if sampling.always_eval_first:
                anchors.add(evaluable_indices[0])
            if sampling.always_eval_last:
                anchors.add(evaluable_indices[-1])

        # Error spans and their immediate neighbours
        for err_n in error_indices:
            anchors.add(err_n)
            pos = evaluable_indices.index(err_n)
            if pos > 0:
                anchors.add(evaluable_indices[pos - 1])
            if pos < len(evaluable_indices) - 1:
                anchors.add(evaluable_indices[pos + 1])

        # LLM spans that immediately follow a large tool output
        anchors.update(post_large_tool_candidates)

        eval_pos_map: Dict[int, int] = {n: i for i, n in enumerate(evaluable_indices)}
        return anchors, eval_pos_map

    def _should_evaluate_span(
        self,
        span_index: int,
        eval_pos_map: Dict[int, int],
        anchors: set,
        sampling: SamplingConfig,
    ) -> bool:
        """Return True if this span should be sent to MCE under the sampling strategy.

        Uses a deterministic hash of span_index so repeated runs on the same session
        always produce the same sampling decisions.
        """
        import hashlib as _hashlib

        if sampling.strategy == "none":
            return True

        if span_index in anchors:
            return True

        total_evaluable = len(eval_pos_map)
        if total_evaluable <= 1:
            return True

        pos = eval_pos_map.get(span_index, 0)
        norm_pos = pos / max(total_evaluable - 1, 1)

        if norm_pos >= 0.70:
            return True  # late zone: always evaluate

        rate = sampling.early_rate if norm_pos < 0.40 else sampling.mid_rate

        # Deterministic hash — same session always gets same sampling decisions
        digest = _hashlib.md5(str(span_index).encode()).digest()[:4]
        h = int.from_bytes(digest, "little")
        return (h / 0xFFFFFFFF) < rate

    # ================================================================
    # Core: evaluate a session
    # ================================================================

    def evaluate_session(
        self,
        session_id: str,
        policy_override: Optional[str] = None,
    ) -> SessionResult:
        """Query session spans through the API library, then evaluate in-process."""
        try:
            spans = self.fetch_spans_for_session(session_id)
        except Exception as exc:
            logger.error("Error fetching session %s: %s", session_id, exc)
            return SessionResult(session_id=session_id, error=str(exc))
        return self.evaluate_spans(
            spans, session_id=session_id, policy_override=policy_override
        )

    def evaluate_spans(
        self,
        spans: Iterable[SpanInput],
        *,
        session_id: str,
        policy_override: Optional[str] = None,
    ) -> SessionResult:
        """Evaluate one session's spans with no retrieval or persistence side effects.

        Input uses the existing PascalCase OTel export format (SpanId, Timestamp,
        SpanAttributes, etc.). Spans are copied before chronological processing.
        Use EvaluationEngine for concurrent evaluations. This compatibility
        processor executes one trajectory at a time.
        """
        try:
            self._last_cross_span_usage = None
            self._last_final_outcome_usage = None
            raw_spans = deepcopy([dict(span) for span in spans])

            if not raw_spans:
                return SessionResult(
                    session_id=session_id,
                    error="No spans found for session",
                )

            raw_spans = self._sort_spans_chronologically(raw_spans)
            raw_spans = self._deduplicate_spans(raw_spans)
            extracted_system_message = self._extract_system_message(raw_spans)
            system_message = (
                policy_override.strip()
                if isinstance(policy_override, str) and policy_override.strip()
                else extracted_system_message
            )
            tool_defs = self._extract_tool_definitions(raw_spans)
            spans_by_id = {
                str(span.get("SpanId")): span
                for span in raw_spans
                if span.get("SpanId")
            }

            total_spans = len(raw_spans)
            current_score = 0.0
            failures: List[MetricFailure] = []
            intent_events: List[Dict[str, Any]] = []
            span_metric_results: List[SpanMetricResult] = []
            mce_call_attempts = 0
            mce_call_successes = 0
            mce_call_failures = 0
            mce_spans_evaluated = 0
            spans_sampled_out = 0
            last_mce_error: Optional[str] = None
            mce_prompt_tokens = 0
            mce_completion_tokens = 0
            mce_total_tokens = 0

            # Adaptive span sampling — lightweight pre-scan (zero MCE calls)
            sampling_cfg: Optional[SamplingConfig] = self.options.sampling
            use_sampling = sampling_cfg is not None and sampling_cfg.strategy != "none"
            anchors: set = set()
            eval_pos_map: Dict[int, int] = {}
            if use_sampling and sampling_cfg is not None:
                anchors, eval_pos_map = self._build_sampling_plan(
                    raw_spans, spans_by_id, sampling_cfg
                )
                logger.info(
                    f"[{session_id}] Sampling: strategy={sampling_cfg.strategy} | "
                    f"evaluable={len(eval_pos_map)} | anchors={sorted(anchors)}"
                )

            traj_ctx = TrajectoryContext(
                policy_text=system_message,
                tool_definitions=tool_defs,
                coordination_context=self._extract_coordination_context(raw_spans),
                adapter_ingestion="incremental",
            )
            traj_ctx.declare_roster(self._declared_roster(raw_spans, spans_by_id))
            root_request = SpanNormalizer.extract_root_request(raw_spans)
            traj_ctx.declare_root_request(root_request)
            self._ingest_agent_semantic_contracts(traj_ctx, raw_spans, root_request)
            app_name = raw_spans[0].get("ServiceName", "") if raw_spans else ""

            use_fatal_mode = self.options.use_fatal_mode
            skip_next_llm = False

            for n, raw_span in enumerate(raw_spans):
                span_dict = self._otel_trace_to_span_dict(
                    raw_span, spans_by_id=spans_by_id
                )
                entity_type = span_dict["entity_type"]
                entity_name = span_dict["entity_name"]

                logger.info(
                    f"[{session_id}] Span {n + 1}/{total_spans} | "
                    f"type={entity_type} | name={entity_name}"
                )

                if entity_type == "agent":
                    skip_next_llm = self._agent_span_has_routing_or_answer(raw_span)
                    if skip_next_llm:
                        logger.info(
                            f"[{session_id}]   Agent routing/answer detected — "
                            f"will skip next LLM span (dedup)"
                        )
                    traj_ctx.ingest_span(span_dict, span_index=n)
                    continue

                if entity_type not in ("tool", "llm"):
                    traj_ctx.ingest_span(span_dict, span_index=n)
                    continue

                if entity_type == "llm" and skip_next_llm:
                    skip_next_llm = False
                    logger.info(
                        f"[{session_id}]   Skipping LLM span (dedup: "
                        f"agent already captured routing/answer)"
                    )
                    traj_ctx.ingest_span(span_dict, span_index=n)
                    continue

                if entity_type == "tool":
                    skip_next_llm = False

                metrics_to_run = self._metrics_for_span(span_dict)
                if not metrics_to_run:
                    traj_ctx.ingest_span(span_dict, span_index=n)
                    continue

                # Adaptive sampling gate — skipped spans still feed TrajectoryContext
                if use_sampling and sampling_cfg is not None:
                    if not self._should_evaluate_span(
                        n, eval_pos_map, anchors, sampling_cfg
                    ):
                        logger.info(
                            f"[{session_id}]   [SAMPLED OUT] span {n} ({entity_type}/{entity_name})"
                        )
                        spans_sampled_out += 1
                        traj_ctx.ingest_span(span_dict, span_index=n)
                        continue

                if span_dict.get("contains_error"):
                    logger.warning(
                        f"[{session_id}]   ERROR span — auto-failing all metrics"
                    )
                    for metric_name in metrics_to_run:
                        span_metric_results.append(
                            SpanMetricResult(
                                span_index=n,
                                span_id=str(raw_span.get("SpanId", "")),
                                trace_id=str(raw_span.get("TraceId", "")),
                                span_type=entity_type,
                                entity_name=entity_name,
                                metric_name=metric_name,
                                score=0.0,
                                reasoning="Auto-failed: span contains error",
                            )
                        )
                        if self._is_intent_metric(metric_name):
                            intent_events.append(
                                {
                                    "score": 0.0,
                                    "span_index": n,
                                    "span_type": entity_type,
                                    "entity_name": entity_name,
                                    "reasoning": "Auto-failed: span contains error",
                                    "output_payload": span_dict.get("output_payload"),
                                }
                            )
                        else:
                            failures.append(
                                MetricFailure(
                                    metric_name=metric_name,
                                    score=0.0,
                                    reasoning="Auto-failed: span contains error",
                                    span_index=n,
                                    span_type=entity_type,
                                    input_payload=span_dict.get("input_payload"),
                                    output_payload=span_dict.get("output_payload"),
                                    entity_name=entity_name,
                                    span_id=span_dict.get("span_id", ""),
                                    policy=system_message,
                                )
                            )
                    traj_ctx.ingest_span(span_dict, span_index=n)
                    continue

                context_state = traj_ctx.retrieve_for_state_delta(span_dict)
                compact_span = self._compact_span_delta(span_dict)
                mce_spans_evaluated += 1
                mce_call_attempts += 1
                try:
                    mce_response = self.compute_span_state_delta(
                        span_dict,
                        context_state=context_state,
                        policy=system_message,
                        metrics=metrics_to_run,
                    )
                    if not mce_response.get("results"):
                        internal_errors = mce_response.get("failed_metrics", [])
                        err_msg = (
                            internal_errors[0].get("error_message", "unknown")
                            if internal_errors
                            else "empty results"
                        )
                        logger.error(
                            f"[{session_id}] Combined span judge returned no results: "
                            f"{err_msg}"
                        )
                        mce_call_failures += 1
                        last_mce_error = err_msg
                        traj_ctx.ingest_span(span_dict, span_index=n)
                        continue

                    mce_call_successes += 1
                    mce_usage = (
                        mce_response.get("usage")
                        or mce_response.get("token_usage")
                        or {}
                    )
                    mce_prompt_tokens += int(mce_usage.get("prompt_tokens", 0))
                    mce_completion_tokens += int(mce_usage.get("completion_tokens", 0))
                    mce_total_tokens += int(mce_usage.get("total_tokens", 0))
                except Exception as e:
                    logger.error(f"[{session_id}] Combined span judge failed: {e}")
                    mce_call_failures += 1
                    last_mce_error = str(e)
                    traj_ctx.ingest_span(span_dict, span_index=n)
                    continue

                eval_context = json.dumps(
                    context_state,
                    ensure_ascii=True,
                    default=str,
                )
                for result in mce_response.get("results", []):
                    result_metric = result.get("metric_name", "")
                    value = result.get("value", 0.0)
                    reasoning = result.get("reasoning", "")
                    metric_success = bool(result.get("success", True))

                    try:
                        score_value = float(value)
                    except (ValueError, TypeError):
                        score_value = 0.0

                    if (not metric_success) or score_value < 0:
                        continue

                    if self._is_intent_metric(result_metric):
                        intent_events.append(
                            {
                                "score": score_value,
                                "span_index": n,
                                "span_type": entity_type,
                                "entity_name": entity_name,
                                "reasoning": reasoning,
                                "output_payload": span_dict.get("output_payload"),
                            }
                        )

                    span_metric_results.append(
                        SpanMetricResult(
                            span_index=n,
                            span_id=str(raw_span.get("SpanId", "")),
                            trace_id=str(raw_span.get("TraceId", "")),
                            span_type=entity_type,
                            entity_name=entity_name,
                            metric_name=result_metric,
                            score=score_value,
                            reasoning=reasoning,
                        )
                    )

                    weight = 1.0 if entity_type == "tool" else 0.5
                    current_score += max(0.0, score_value) * weight

                    logger.info(
                        f"[{session_id}]   {result_metric}: "
                        f"score={score_value} | "
                        f"reasoning={reasoning[:120]}{'...' if len(str(reasoning)) > 120 else ''}"
                    )

                    if use_fatal_mode and score_value == 0:
                        if not self._is_intent_metric(result_metric):
                            failures.append(
                                MetricFailure(
                                    metric_name=result_metric,
                                    score=score_value,
                                    reasoning=reasoning,
                                    span_index=n,
                                    span_type=entity_type,
                                    input_payload=compact_span.get("current_input"),
                                    output_payload=compact_span.get("current_output"),
                                    eval_context=eval_context,
                                    entity_name=entity_name,
                                    span_id=span_dict.get("span_id", ""),
                                    policy=system_message,
                                )
                            )

                traj_ctx.ingest_span(span_dict, span_index=n)

            self._synchronize_final_answer(traj_ctx, raw_spans)
            traj_ctx.finalize_state()

            if (
                mce_call_attempts > 0
                and mce_call_successes == 0
                and mce_call_failures > 0
            ):
                return SessionResult(
                    session_id=session_id,
                    app_name=app_name,
                    error=(
                        f"All MCE metric calls failed ({mce_call_failures}/{mce_call_attempts}). "
                        f"Last error: {last_mce_error or 'unknown'}"
                    ),
                )

            avg_score = current_score / total_spans if total_spans > 0 else 0

            if use_fatal_mode:
                orig_count = len(failures)
                failures = [
                    f
                    for f in failures
                    if not (
                        f.span_type == "llm"
                        and self._is_effectively_empty_payload(f.output_payload)
                    )
                ]
                dropped = orig_count - len(failures)
                if dropped:
                    logger.info(
                        f"[{session_id}] Dropped {dropped} failure(s) from "
                        f"empty-output LLM spans (orchestration artifacts)"
                    )

            if use_fatal_mode:
                loop_failure = self._detect_loop_pattern(traj_ctx)
                if loop_failure:
                    logger.info(
                        f"[{session_id}] Loop pattern detected: "
                        f"{loop_failure.reasoning[:120]}"
                    )
                    failures.append(loop_failure)

            intent_states = self._resolve_intent_states(intent_events, total_spans)
            unsatisfied_intents = self._count_unsatisfied_intents(intent_states)

            fatal_failures: List[FailureDetail] = []
            minor_failures: List[FailureDetail] = []
            trajectory_patterns: List[str] = []
            review_tokens = _empty_usage()
            high_level_tokens = _empty_usage()
            high_level_metrics: List[Dict[str, Any]] = []
            trajectory_metric_tokens = _empty_usage()
            trajectory_metric_set: Optional[str] = None
            trajectory_metrics: List[Dict[str, Any]] = []
            use_unified_audit = bool(
                use_fatal_mode and self.options.use_unified_final_audit
            )

            if use_unified_audit:
                (
                    fatal_failures,
                    minor_failures,
                    trajectory_patterns,
                    high_level_metrics,
                    high_level_tokens,
                ) = self._run_unified_final_audit(
                    traj_ctx=traj_ctx,
                    failures=failures,
                    intent_states=intent_states,
                    unsatisfied_intents=unsatisfied_intents,
                    raw_spans=raw_spans,
                    session_id=session_id,
                )

            if use_fatal_mode and not use_unified_audit and failures:
                aftermath = self._build_intent_aftermath(intent_states)
                review_result = run_inter_step_review(
                    failures=failures,
                    trajectory_summary=traj_ctx.get_full_summary(),
                    policy=system_message,
                    llm_client=self.llm_client,
                    aftermath=aftermath,
                )
                fatal_failures = review_result["fatal_failures"]
                minor_failures = review_result["minor_failures"]
                trajectory_patterns = review_result.get("trajectory_patterns", [])
                review_tokens = review_result.get("usage", _empty_usage())

            if not use_unified_audit and fatal_failures and intent_states:
                all_resolved = all(
                    getattr(s, "state", "") in self._RESOLVED_INTENT_STATES
                    for s in intent_states
                )
                if all_resolved:
                    rescued: List[FailureDetail] = []
                    remaining: List[FailureDetail] = []
                    for f in fatal_failures:
                        if getattr(f, "hard_rule_violation", False):
                            remaining.append(f)
                            continue
                        impact = getattr(f, "observed_impact", "") or ""
                        severity = float(getattr(f, "fatality_score", 1.0))
                        if impact == "none" or severity < 0.85:
                            rescued.append(f)
                        else:
                            remaining.append(f)
                    if rescued:
                        logger.info(
                            f"[{session_id}] All-intents-resolved relief: "
                            f"downgrading {len(rescued)} low-confidence "
                            f"fatal(s) to minor"
                        )
                        minor_failures.extend(rescued)
                        fatal_failures = remaining

            if use_fatal_mode and not use_unified_audit and unsatisfied_intents > 0:
                unresolved = [
                    s
                    for s in intent_states
                    if getattr(s, "state", "") in ("failed", "drifting")
                    and int(getattr(s, "occurrences", 0) or 0) >= 2
                    and float(getattr(s, "final_score", 0)) == 0.0
                ]
                unresolved_names = [getattr(s, "name", "?") for s in unresolved]
                logger.info(
                    f"[{session_id}] Trajectory-level intent check: "
                    f"{len(unresolved)} unresolved intent(s): "
                    f"{', '.join(unresolved_names)}"
                )
                for s in unresolved:
                    fatal_failures.append(
                        FailureDetail(
                            metric="IntentRecognition",
                            metric_score=0.0,
                            fatality_score=1.0,
                            reasoning=(
                                f"Intent '{getattr(s, 'name', '?')}' was invoked "
                                f"{getattr(s, 'occurrences', 0)} times across the "
                                f"trajectory but never advanced the user's goal "
                                f"(best score: {getattr(s, 'final_score', 0)})."
                            ),
                            explanation=(
                                "Trajectory-level intent check: the agent repeatedly "
                                "attempted this tool without making progress toward "
                                "the user's stated objective."
                            ),
                            observed_impact="intent_abandonment",
                            confidence=0.9,
                        )
                    )

            trajectory_score = None
            if use_fatal_mode:
                uses_paper_suite = (
                    use_unified_audit
                    and self.options.high_level_metric_suite in {"paper_v1", "paper_v2"}
                )
                scoring_fatal_failures = [
                    failure
                    for failure in fatal_failures
                    if failure.affects_trajectory_score
                ]
                preliminary_pass = (
                    True if uses_paper_suite else unsatisfied_intents == 0
                ) and len(scoring_fatal_failures) == 0

                if preliminary_pass and not use_unified_audit:
                    cross_span_failures = self._cross_validate_final_answer(
                        traj_ctx=traj_ctx,
                        system_message=system_message,
                        session_id=session_id,
                        raw_spans=raw_spans,
                    )
                    for csf in cross_span_failures:
                        is_hard_rule = csf.eval_context == "cross_span_hard_rule"
                        minor_failures.append(
                            FailureDetail(
                                metric=csf.metric_name,
                                metric_score=csf.score,
                                fatality_score=0.3,
                                reasoning=csf.reasoning,
                                explanation=(
                                    "Cross-span audit (informational): "
                                    + (
                                        "hard-rule signal detected in final answer."
                                        if is_hard_rule
                                        else "possible fabrication in final answer."
                                    )
                                ),
                                span_index=csf.span_index,
                                span_type=csf.span_type,
                                observed_impact="informational",
                                confidence=0.3,
                                hard_rule_violation=False,
                            )
                        )

                    final_fatal, final_minor = self._review_final_outcome(
                        traj_ctx=traj_ctx,
                        system_message=system_message,
                        session_id=session_id,
                        intent_states=intent_states,
                        raw_spans=raw_spans,
                    )
                    if final_fatal or final_minor:
                        logger.info(
                            f"[{session_id}] Final outcome review: "
                            f"fatal={len(final_fatal)} minor={len(final_minor)}"
                        )
                    fatal_failures.extend(final_fatal)
                    minor_failures.extend(final_minor)

                scoring_fatal_failures = [
                    failure
                    for failure in fatal_failures
                    if failure.affects_trajectory_score
                ]
                trajectory_score = (
                    0
                    if (
                        scoring_fatal_failures
                        or (unsatisfied_intents > 0 and not uses_paper_suite)
                    )
                    else 1
                )

                if use_unified_audit and not uses_paper_suite:
                    from stateful_evals_be.evaluation.trajectory_context_metrics import (
                        CorrectnessMetric,
                    )

                    high_level_metrics.append(
                        CorrectnessMetric()
                        .evaluate(
                            traj_ctx,
                            stateful_result={
                                "trajectory_score": trajectory_score,
                                "fatal_failures": fatal_failures,
                                "minor_failures": minor_failures,
                            },
                        )
                        .to_payload()
                    )

            trajectory_reasoning = self._build_trajectory_reasoning(
                fatal_failures,
                minor_failures,
                trajectory_score,
            )

            if self.options.trajectory_metrics:
                from stateful_evals_be.evaluation.trajectory_context_metrics import (
                    TRAJECTORY_METRIC_SET,
                )

                trajectory_metrics, trajectory_metric_tokens = (
                    self._run_configured_trajectory_metrics(
                        traj_ctx=traj_ctx,
                        failures=failures,
                        intent_states=intent_states,
                        unsatisfied_intents=unsatisfied_intents,
                        raw_spans=raw_spans,
                        fatal_failures=fatal_failures,
                        minor_failures=minor_failures,
                        trajectory_score=trajectory_score,
                        trajectory_reasoning=trajectory_reasoning,
                        session_id=session_id,
                    )
                )
                trajectory_metric_set = TRAJECTORY_METRIC_SET

            mce_pt = mce_prompt_tokens
            mce_ct = mce_completion_tokens
            mce_tt = mce_total_tokens
            rev_pt = int(review_tokens.get("prompt_tokens", 0))
            rev_ct = int(review_tokens.get("completion_tokens", 0))
            rev_tt = int(review_tokens.get("total_tokens", 0))

            cs_usage = getattr(self, "_last_cross_span_usage", None) or {}
            cs_pt = int(cs_usage.get("prompt_tokens", 0))
            cs_ct = int(cs_usage.get("completion_tokens", 0))
            cs_tt = int(cs_usage.get("total_tokens", 0))
            self._last_cross_span_usage = None

            fo_usage = getattr(self, "_last_final_outcome_usage", None) or {}
            fo_pt = int(fo_usage.get("prompt_tokens", 0))
            fo_ct = int(fo_usage.get("completion_tokens", 0))
            fo_tt = int(fo_usage.get("total_tokens", 0))
            self._last_final_outcome_usage = None

            hl_pt = int(high_level_tokens.get("prompt_tokens", 0)) + int(
                trajectory_metric_tokens.get("prompt_tokens", 0)
            )
            hl_ct = int(high_level_tokens.get("completion_tokens", 0)) + int(
                trajectory_metric_tokens.get("completion_tokens", 0)
            )
            hl_tt = int(high_level_tokens.get("total_tokens", 0)) + int(
                trajectory_metric_tokens.get("total_tokens", 0)
            )

            sampling_summary = (
                f"sampled_out={spans_sampled_out} | "
                f"mce_evaluated={mce_spans_evaluated} | "
                if use_sampling
                else ""
            )
            logger.info(
                f"[{session_id}] === SESSION COMPLETE === "
                f"spans={total_spans} | {sampling_summary}"
                f"score={current_score:.2f} | "
                f"avg={avg_score:.3f} | failures={len(failures)} | "
                f"fatal={len(fatal_failures)} | minor={len(minor_failures)} | "
                f"unsatisfied_intents={unsatisfied_intents} | "
                f"trajectory_score={trajectory_score} | "
                f"patterns={trajectory_patterns}"
            )

            token_usage = TokenUsage(
                mce_prompt_tokens=mce_pt,
                mce_completion_tokens=mce_ct,
                mce_total_tokens=mce_tt,
                review_prompt_tokens=rev_pt,
                review_completion_tokens=rev_ct,
                review_total_tokens=rev_tt,
                cross_span_prompt_tokens=cs_pt,
                cross_span_completion_tokens=cs_ct,
                cross_span_total_tokens=cs_tt,
                final_outcome_prompt_tokens=fo_pt,
                final_outcome_completion_tokens=fo_ct,
                final_outcome_total_tokens=fo_tt,
                high_level_prompt_tokens=hl_pt,
                high_level_completion_tokens=hl_ct,
                high_level_total_tokens=hl_tt,
                prompt_tokens=mce_pt + rev_pt + cs_pt + fo_pt + hl_pt,
                completion_tokens=mce_ct + rev_ct + cs_ct + fo_ct + hl_ct,
                total_tokens=mce_tt + rev_tt + cs_tt + fo_tt + hl_tt,
            )
            cost_estimate = estimate_token_cost(
                token_usage,
                self.llm_config.LLM_MODEL_NAME,
            )

            return SessionResult(
                session_id=session_id,
                app_name=app_name,
                trajectory_score=trajectory_score,
                trajectory_reasoning=trajectory_reasoning,
                unsatisfied_intents=unsatisfied_intents,
                intent_states=intent_states,
                total_spans=total_spans,
                mce_spans_evaluated=mce_spans_evaluated,
                mce_calls=mce_call_successes,
                spans_sampled_out=spans_sampled_out,
                current_score=current_score,
                avg_score=avg_score,
                use_fatal_mode=use_fatal_mode,
                total_failures=len(failures),
                fatal_failures=fatal_failures,
                minor_failures=minor_failures,
                span_metric_results=span_metric_results,
                trajectory_patterns=trajectory_patterns,
                high_level_metric_suite=self.options.high_level_metric_suite,
                high_level_metrics=high_level_metrics,
                trajectory_metric_set=trajectory_metric_set,
                trajectory_metrics=trajectory_metrics,
                token_usage=token_usage,
                cost_estimate=cost_estimate,
            )

        except Exception as e:
            error_str = str(e)
            logger.error(f"Error processing session {session_id}: {error_str}")

            # Whole-session retries belong to the caller. Re-fetching here would
            # violate evaluate_spans' input boundary and repeat billed model work.
            return SessionResult(session_id=session_id, error=error_str)

    # ================================================================
    # Trajectory reasoning builder
    # ================================================================

    @staticmethod
    def _build_trajectory_reasoning(
        fatal_failures: List[FailureDetail],
        minor_failures: List[FailureDetail],
        trajectory_score: Optional[int],
    ) -> str:
        """Stringify fatal/minor failure details as the trajectory_score reasoning."""

        def _failure_to_dict(f: FailureDetail, classification: str) -> Dict[str, Any]:
            return {
                "classification": classification,
                "metric": f.metric,
                "span_index": f.span_index,
                "span_id": f.span_id,
                "span_type": f.span_type,
                "entity_name": f.entity_name,
                "metric_score": f.metric_score,
                "fatality_score": f.fatality_score,
                "reasoning": f.reasoning,
                "explanation": f.explanation,
                "observed_impact": f.observed_impact,
                "confidence": f.confidence,
                "hard_rule_violation": f.hard_rule_violation,
                "self_corrected": f.self_corrected,
                "affects_trajectory_score": f.affects_trajectory_score,
            }

        payload: Dict[str, Any] = {
            "trajectory_score": trajectory_score,
            "fatal_failures": [_failure_to_dict(f, "FATAL") for f in fatal_failures],
            "minor_failures": [_failure_to_dict(f, "MINOR") for f in minor_failures],
            "total_fatal": len(fatal_failures),
            "total_minor": len(minor_failures),
        }
        return json.dumps(payload, ensure_ascii=False, default=str)

    # ================================================================
    # Batch: evaluate multiple sessions
    # ================================================================

    def run_evaluation(
        self,
        session_ids: List[str],
        policy_overrides: Optional[Dict[str, str]] = None,
    ) -> EvalSummary:
        """Compatibility batch entry point; isolate evaluation state per session."""
        from stateful_evals_be.evaluation.engine import EvaluationEngine

        return EvaluationEngine(
            llm_config=self.llm_config, options=self.options
        ).evaluate_sessions(
            session_ids,
            span_loader=self.fetch_spans_for_session,
            policy_overrides=policy_overrides,
        )


def _same_answer_text(first: str, second: str) -> bool:
    """True when two renderings are the same delivered answer."""

    def normalize(text: str) -> str:
        visible = re.sub(
            r"<\|?channel\|?>\s*(?:thought|analysis|final)?",
            " ",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        return " ".join(visible.split()).casefold().strip(" .!")

    left, right = normalize(first), normalize(second)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return shorter in longer and len(shorter) >= 0.9 * len(longer)
