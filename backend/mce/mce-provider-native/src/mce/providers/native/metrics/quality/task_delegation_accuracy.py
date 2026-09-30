#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.utils import llm_g_eval_score


class TaskDelegationAccuracy(Metric):
    """Determines if the task delegation was accurate with respect to the input."""

    metadata = SpecRegistry.require("TaskDelegationAccuracy").metadata

    PROMPT_TEMPLATE = """
You are evaluating Task Delegation Accuracy in a Multi-Agent System.

Agent Input (Received Task):
{agent_input}

Agent Output (Actions/Decisions Taken):
{agent_output}

Evaluation Criteria:
1. Did the agent correctly interpret the task request?
2. Are the actions taken fully aligned with the delegated task?
3. Are there any misinterpretations, skipped steps, or incorrect decisions?

Scoring Scale (1-5):
1 - Complete failure: agent entirely misunderstood or ignored the task.
2 - Significant failure: major misinterpretation or many steps missed.
3 - Partial: understood the core request but missed key details or constraints.
4 - Good: mostly correct with only minor gaps or imprecisions.
5 - Excellent: task fully and accurately understood and executed.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            text_fields=["inputContent", "outputContent", "agentName"]
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        agent_input = context.get("inputContent") or context.get("input_text") or ""
        agent_output = context.get("outputContent") or context.get("output_text") or ""
        if not (agent_input and agent_output):
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="Missing required agent data",
            )

        prompt = self.PROMPT_TEMPLATE.format(
            agent_input=agent_input,
            agent_output=agent_output,
        )
        score, reasoning, raw = llm_g_eval_score(self, prompt)
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=score,
            metric_class=self.ontology_class,
            reasoning=reasoning,
            metadata={"raw_score": raw, "scale": "1-5"},
        )
