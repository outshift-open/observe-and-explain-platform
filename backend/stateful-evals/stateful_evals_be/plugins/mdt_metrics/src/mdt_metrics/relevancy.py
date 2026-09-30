#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from typing import List, Optional

from metrics_computation_engine.metrics.base import BaseMetric

from ._binary_metric_utils import judge_binary, stringify_payload


class Relevancy(BaseMetric):
    """The trajectory is internally non-contradictory and conclusions follow from premises.

    Evaluates logical consistency at two levels:
    - Intra-step: Does this span contradict itself?
    - Inter-step: Does this span contradict prior claims, decisions, or evidence?

    Also checks reasoning validity: do the conclusions in this span follow
    logically from the available premises?
    """

    REQUIRED_PARAMETERS = [
        "input_payload",
        "output_payload",
        "entity_name",
    ]

    RELEVANCY_PROMPT = """You are evaluating the logical consistency of an AI agent span at both the intra-step and inter-step level.

## Span Details
Span Type: {span_type}
Entity Name: {entity_name}

## Span Input
{span_input}

## Span Output
{span_output}

## Tool Definition (if available)
{tool_definition}

## Reasoning History (prior claims, decisions, and evidence)
{context}

## Policy
{policy}

## What "logical consistency" means

### Intra-step consistency
Within this single span, the agent's output must not contradict itself.
- Asserting X and not-X in the same response
- Drawing a conclusion that doesn't follow from the stated premises
- Taking an action that contradicts the stated reasoning

### Inter-step consistency
Across the trajectory, this span must not contradict prior established facts.
- Claiming a state that contradicts a prior tool output
- Reversing a decision without acknowledging the change
- Asserting completion of something that prior evidence shows is incomplete
- Repeating an approach that was already shown to fail (loop entrapment)

### Reasoning validity
The inferential steps must be sound.
- Conclusions must follow from premises
- Actions must be justified by the available evidence
- Generalizations must not be drawn from insufficient evidence

## Evaluation protocol
1. Extract concrete claims from this span (IDs, values, states, decisions).
2. Check intra-step: does the output contain internal contradictions?
3. Check inter-step: compare claims against reasoning history for conflicts.
4. Check reasoning: do conclusions follow from available evidence?
5. Score 0 only when at least one explicit contradiction or invalid
   inference is identified.

## Contradiction categories
- Identifier mismatch (referring to entity A but acting on entity B)
- Value/constraint mismatch (user said X but agent used Y)
- State transition mismatch (tool shows state A, agent claims state B)
- Completion claim contradicted by evidence (says "done" but it's not)
- Repeated failed approach (trying same thing that already failed)
- Invalid inference (conclusion doesn't follow from premises)

## Scoring
- Score 1: No contradictions or invalid reasoning found. OR consistent
  course correction with explicit acknowledgment of the change.
- Score 0: At least one explicit contradiction pair or provably invalid
  inference identified.

## Mandatory evidence for score 0
You MUST cite a specific contradiction pair:
- Claim A (from this span) vs Evidence B (from history or this span)
If you cannot produce both sides from explicit evidence, score MUST be 1.

## Calibration
- Course corrections with explicit reasoning ("I initially thought X but
  tool output shows Y, so I'll do Z instead") are CONSISTENT: score 1.
- Missing visibility in excerpts is uncertainty, not contradiction: score 1.
- Ambiguity or inference/speculation is not contradiction: score 1.
- Planning language changing approach: score 1 (plans can evolve).
- Procedural/formatting/style concerns: score 1 (not logical issues).
- Partial excerpts without explicit conflict: score 1."""

    def __init__(self, metric_name: Optional[str] = None):
        super().__init__()
        self.name = metric_name or "Relevancy"
        self.aggregation_level = "span"
        self.required = {"entity_type": ["tool", "llm"]}

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
                error_message="Missing required data for logical consistency computation",
                span_ids=[data.span_id],
                session_ids=[data.session_id],
            )

        if self.jury:
            prompt = self.RELEVANCY_PROMPT.format(
                span_type=data.entity_type,
                entity_name=data.entity_name,
                span_input=stringify_payload(data.input_payload),
                span_output=stringify_payload(data.output_payload),
                tool_definition=stringify_payload(data.tool_definition),
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
