#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from typing import List, Optional

from metrics_computation_engine.metrics.base import BaseMetric

from ._binary_metric_utils import judge_binary, stringify_payload


class Groundedness(BaseMetric):
    """Every factual claim and parameter traces to evidence or verifiable truth.

    Evaluates whether the agent's output is grounded in available evidence
    sources: tool outputs (authoritative), user statements, and policy rules.
    Agent prior outputs are NOT evidence — they are the subject of evaluation.
    """

    REQUIRED_PARAMETERS = [
        "input_payload",
        "output_payload",
        "entity_name",
    ]

    GROUNDEDNESS_PROMPT = """You are evaluating whether an AI agent's output is factually grounded in available evidence.

## Span Details
Span Type: {span_type}
Entity Name: {entity_name}

## Agent Input
{span_input}

## Agent Output
{span_output}

## Evidence Sources (Source of Truth)
{context}

## Policy
{policy}

## What "grounded" means
A claim is grounded if it traces to at least one of:
1. A tool output from this trajectory (authoritative — highest priority)
2. An explicit user statement from this trajectory
3. The policy document (defines valid rules and constraints)
4. A verifiable universal truth (laws of physics, mathematical facts)

A claim is UNGROUNDED if it contradicts available evidence or fabricates
specifics (IDs, values, states, dates) not present in any evidence source.

## Evaluation protocol
For each factual assertion in the agent's output:
1. Identify the claim (what entity, what value, what state).
2. Search evidence sources for supporting or contradicting evidence.
3. If supported or no evidence exists either way: grounded.
4. If explicit contradicting evidence exists: ungrounded.

## Scoring
- Score 1: All claims are supported, OR no factual claims present, OR
  uncertain without explicit contradicting evidence.
- Score 0: At least one decision-critical factual claim explicitly
  contradicts available evidence.

## Calibration
- Tool outputs are authoritative evidence — contradicting a tool output is
  a strong signal of ungroundedness.
- Empty, brief, or non-substantive responses: score 1.
- Procedural, formatting, or policy-compliance issues are out of scope
  unless they produce an explicit factual contradiction.
- Planning language ("I will check...", "Let me look into...") is not a
  factual claim and cannot be ungrounded.
- If most claims are supported and only peripheral details are uncertain
  or mildly overstated: score 1.
- Missing visibility in the evidence excerpt is uncertainty, not
  contradiction — score 1.
- Score 0 requires you to cite BOTH the specific claim AND the specific
  contradicting evidence."""

    def __init__(self, metric_name: Optional[str] = None):
        super().__init__()
        self.name = metric_name or "Groundedness"
        self.aggregation_level = "span"
        self.required = {"entity_type": ["llm"]}

    @property
    def required_parameters(self) -> List[str]:
        return self.REQUIRED_PARAMETERS

    def validate_config(self) -> bool:
        return True

    def init_with_model(self, model) -> bool:
        self.jury = model
        return True

    def get_model_provider(self):
        return self.get_default_provider()

    def create_model(self, llm_config):
        return self.create_native_model(llm_config)

    async def compute(self, data, **context):
        if data.entity_type not in self.required["entity_type"] or not (
            data.input_payload and data.output_payload and data.entity_name
        ):
            return self._create_error_result(
                category="agent",
                app_name=data.app_name,
                entities_involved=[data.entity_name],
                error_message="Missing required data for groundedness computation",
                span_ids=[data.span_id],
                session_ids=[data.session_id],
            )

        if self.jury:
            prompt = self.GROUNDEDNESS_PROMPT.format(
                span_type=data.entity_type,
                entity_name=data.entity_name,
                span_input=stringify_payload(data.input_payload),
                span_output=stringify_payload(data.output_payload),
                context=stringify_payload(context.get("context", "")),
                policy=stringify_payload(context.get("policy", "")),
            )

            score, reasoning = await judge_binary(self.jury, prompt)
            return self._create_success_result(
                score,
                category="agent",
                app_name=data.app_name,
                agent_id=data.agent_id,
                reasoning=reasoning,
                entities_involved=[data.entity_name],
                span_ids=[data.span_id],
                session_ids=[data.session_id],
            )

        return self._create_error_result(
            category="agent",
            app_name=data.app_name,
            entities_involved=[data.entity_name],
            error_message="Please configure your LLM credentials",
            span_ids=[data.span_id],
            session_ids=[data.session_id],
        )
