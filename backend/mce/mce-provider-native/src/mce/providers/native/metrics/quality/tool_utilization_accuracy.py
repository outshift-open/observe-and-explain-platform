#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import concurrent.futures
import logging
import os
from typing import Any
from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.utils import llm_g_eval_score
from mce.providers.native.metrics.quality.tool_utilization_accuracy_workaround import (
    resolve_tool_call_fields,
)

logger = logging.getLogger(__name__)


class ToolUtilizationAccuracy(Metric):
    """Determines if the tool usage was accurate with respect to the input."""

    metadata = SpecRegistry.require("ToolUtilizationAccuracy").metadata

    PROMPT_TEMPLATE = """
You are evaluating Tool Utilization Accuracy for an AI agent.

Agent Input:
{tool_input}

Tool Called: {tool_name}
Tool Definition / Schema: {tool_definition}

Tool Output:
{tool_output}

Evaluation Criteria:
1. Was the correct tool selected for this input? Would any other tool have been more appropriate?
2. Were the tool arguments well-formed and correctly derived from the input?
3. Does the tool output adequately address the need expressed in the input?

Scoring Scale (1-5):
1 - Wrong tool or completely malformed call: tool selection makes no sense for the input.
2 - Poor: tool is marginally relevant but arguments are incorrect or output is unhelpful.
3 - Moderate: plausible tool choice but arguments have errors or output only partially useful.
4 - Good: correct tool, mostly well-formed call, output adequately addresses the input.
5 - Excellent: optimal tool selected, perfectly constructed call, output fully satisfies the input.

Output format:
Reasoning: <step-by-step analysis>
Score: <1-5>
    """

    @property
    def input_requirements(self) -> MetricRequirements:
        return SpecRegistry.require("ToolUtilizationAccuracy").input_requirements

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        # Session/Agent level: aggregate over tool_spans → average score
        tool_spans = context.get("tool_spans", [])
        if tool_spans and "toolArguments" not in context:
            return self._compute_session_avg(resource_id, context, tool_spans)

        # EXECUTION_ELEMENT level: single ToolCall
        return self._compute_single(resource_id, context)

    def _compute_single(
        self, resource_id: str, context: dict[str, Any]
    ) -> MetricResult:
        """Compute for a single ToolCall node."""
        tool_input, tool_output, tool_name, tool_definition, missing = (
            resolve_tool_call_fields(context)
        )

        if missing:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning=f"Missing required tool data: {missing}",
            )

        prompt = self.PROMPT_TEMPLATE.format(
            tool_input=tool_input,
            tool_output=tool_output,
            tool_name=tool_name,
            tool_definition=tool_definition,
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

    def _compute_session_avg(
        self,
        resource_id: str,
        context: dict[str, Any],
        tool_spans: list[dict[str, Any]],
    ) -> MetricResult:
        """
        Average ToolUtilizationAccuracy over all ToolCall spans in the session.
        Reads ontology attribute names directly: toolArguments, outputContent, toolName.
        Tool calls without output are skipped (not scored).
        """
        scores: list[float] = []
        skipped = 0
        evaluable_calls: list[dict[str, Any]] = []
        for tc in tool_spans:
            tool_input, tool_output, tool_name, tool_definition, missing = (
                resolve_tool_call_fields(tc)
            )
            if missing:
                skipped += 1
                logger.warning(
                    "ToolUtilizationAccuracy: skipping ToolCall %s — missing %s",
                    tc.get("executionId", "?"),
                    missing,
                )
                continue
            evaluable_calls.append(
                {
                    "execution_id": tc.get("executionId", "?"),
                    "prompt": self.PROMPT_TEMPLATE.format(
                        tool_input=tool_input,
                        tool_output=tool_output,
                        tool_name=tool_name,
                        tool_definition=tool_definition,
                    ),
                }
            )

        if not evaluable_calls:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=0.0,
                metric_class=self.ontology_class,
                reasoning=f"No evaluable ToolCalls in session (skipped={skipped}, total={len(tool_spans)})",
            )

        max_workers = self._resolve_parallel_workers()
        total = len(evaluable_calls)
        logger.info(
            "ToolUtilizationAccuracy[%s]: scoring %d ToolCalls with max_workers=%d (skipped=%d)",
            resource_id,
            total,
            max_workers,
            skipped,
        )

        def _score_call(item: dict[str, str]) -> tuple[str, float]:
            score, _, _ = llm_g_eval_score(self, item["prompt"])
            return item["execution_id"], score

        completed = 0
        log_every = 1 if total <= 10 else max(1, total // 4)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_call = {
                executor.submit(_score_call, item): item["execution_id"]
                for item in evaluable_calls
            }
            for future in concurrent.futures.as_completed(future_to_call):
                execution_id, score = future.result()
                scores.append(score)
                completed += 1
                if completed == total or completed % log_every == 0:
                    logger.info(
                        "ToolUtilizationAccuracy[%s]: progress %d/%d (last=%s)",
                        resource_id,
                        completed,
                        total,
                        execution_id,
                    )

        avg = sum(scores) / len(scores)
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=avg,
            metric_class=self.ontology_class,
            reasoning=f"Average ToolUtilizationAccuracy over {len(scores)} tool calls (skipped={skipped})",
            metadata={
                "scores": scores,
                "evaluated": len(scores),
                "skipped": skipped,
                "scale": "1-5",
            },
        )

    def _resolve_parallel_workers(self) -> int:
        configured = getattr(self, "_mce_max_workers", None)
        if isinstance(configured, int) and configured >= 1:
            return configured

        env_value = os.getenv("MCE_ENGINE_MAX_WORKERS")
        if env_value:
            try:
                parsed = int(env_value)
                if parsed >= 1:
                    return parsed
            except ValueError:
                logger.warning(
                    "ToolUtilizationAccuracy: invalid MCE_ENGINE_MAX_WORKERS=%r, using default",
                    env_value,
                )

        return 8
