#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from typing import List, Optional

from metrics_computation_engine.metrics.base import BaseMetric

from ._binary_metric_utils import judge_binary, stringify_payload


class IntentRecognition(BaseMetric):
    """Every requirement (user-stated and system-level) is identified, tracked, and addressed.

    Evaluates whether the agent properly recognizes all pending user requests
    and policy constraints, and whether this span makes appropriate progress
    toward satisfying them.  Intents include explicit user requests, implicit
    sub-tasks, and policy-defined constraints.
    """

    REQUIRED_PARAMETERS = [
        "input_payload",
        "output_payload",
        "entity_name",
    ]

    INTENT_RECOGNITION_PROMPT = """You are evaluating whether an AI agent properly identifies, tracks, and addresses all pending requirements in this span.

## Span Details
Span Type: {span_type}
Entity Name: {entity_name}

## Span Input
{span_input}

## Span Output
{span_output}

## Tool Definition (if available)
{tool_definition}

## Intent Register (accumulated state of all tracked requirements)
{context}

## Policy (defines system-level constraints that are also requirements)
{policy}

## What "intent recognition" means
An intent is any requirement the agent must address:
- Explicit user requests ("cancel my order", "book a flight to NYC")
- Implicit sub-tasks required to fulfill user requests (e.g., looking up
  order details before cancelling)
- Policy-mandated constraints (e.g., "must confirm before modifying",
  "require authentication first")
- Planned actions the agent committed to in prior steps

"Address" does NOT mean "grant." An intent is satisfied when the agent:
- Fulfills the request, OR
- Acknowledges the request and rejects it per policy with an explanation

A rejected-per-policy intent is SATISFIED. The agent's obligation is to
the policy, not to the user's desired outcome. A user wanting a refund
that the agent correctly denies because of policy means the intent was
handled — the agent did its job.

"Missed intents" are intents the agent forgot, drifted away from, or
never acknowledged at all.

## Evaluation protocol
1. From the intent register, identify what requirements are currently
   PENDING (not yet fulfilled or rejected per policy).
2. Determine what this span does:
   - Tool span: what operation was executed and with what parameters?
   - LLM span: what commitment, decision, or response was made?
3. Assess alignment on three axes:
   a. Does the span's action/response relate to a pending requirement?
   b. Does it make progress (even partial) toward fulfilling or
      appropriately resolving (including policy-based rejection) it?
   c. Does it drop, forget, or ignore a requirement that should be
      addressed at this point?

## Scoring
- Score 1: The span addresses, progresses, or appropriately acknowledges
  pending requirements. OR the span is a legitimate intermediate step
  (setup, retrieval, disambiguation). OR the span rejects a user request
  per policy with explanation (policy compliance = intent handled).
- Score 0: The span explicitly drops, forgets, or ignores a pending
  requirement that it should have addressed.

## Mandatory evidence for score 0
You MUST identify BOTH sides of the mismatch:
- The specific pending requirement (from user or policy), AND
- The specific action/response that drops or ignores it.
If you cannot cite both from explicit evidence, score MUST be 1.

## Calibration
- Partial progress on one sub-goal while others wait: score 1.
- Setup, retrieval, or disambiguation steps: score 1.
- Policy-valid refusal or escalation with rationale: score 1.
- Agent denying user request because policy prohibits it: score 1.
- Not every span must address every pending intent — only the ones
  contextually appropriate for this step.
- Procedural sequencing concerns alone are NOT intent failures unless
  they cause a requirement to be dropped.
- Agent planning ("I will do X next") maintains intent tracking: score 1.
- An agent that addresses 3 of 4 requirements and is still working on the
  4th: score 1 (it's in progress, not dropped)."""

    def __init__(self, metric_name: Optional[str] = None):
        super().__init__()
        self.name = metric_name or "IntentRecognition"
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
                error_message="Missing required data for intent recognition computation",
                span_ids=[data.span_id],
                session_ids=[data.session_id],
            )

        if self.jury:
            prompt = self.INTENT_RECOGNITION_PROMPT.format(
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
                float(score),
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
