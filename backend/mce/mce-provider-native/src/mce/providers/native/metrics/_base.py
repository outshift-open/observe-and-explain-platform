#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.providers.native.utils import (
    extract_conversation_text,
    extract_query_response,
    llm_g_eval_score,
)


class _BaseLLMJudgeConversationMetric(Metric):
    """Base for LLM-judge metrics that evaluate a full conversation transcript.

    Subclasses must define ``PROMPT_TEMPLATE`` as a class attribute with a
    ``{conversation}`` placeholder. ``compute()`` extracts the conversation,
    runs G-Eval scoring, and returns a normalized ``MetricResult``.
    """

    PROMPT_TEMPLATE: str  # must be defined by subclass

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(
            text_fields=["conversation_data", "conversation_text", "transcript"]
        )

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        conversation = extract_conversation_text(context)
        if not conversation:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="No conversation data",
            )
        prompt = self.PROMPT_TEMPLATE.format(conversation=conversation)
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


class _BaseLLMJudgeQAMetric(Metric):
    """Base for LLM-judge metrics that evaluate a query / response pair.

    Subclasses must define ``PROMPT_TEMPLATE`` as a class attribute with
    ``{query}`` and ``{response}`` placeholders.
    """

    PROMPT_TEMPLATE: str  # must be defined by subclass

    @property
    def input_requirements(self) -> MetricRequirements:
        return MetricRequirements(text_fields=["input_query", "final_response"])

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        query, response = extract_query_response(context)
        if not (query and response):
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning="Missing query/response data",
            )
        prompt = self.PROMPT_TEMPLATE.format(query=query, response=response)
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
