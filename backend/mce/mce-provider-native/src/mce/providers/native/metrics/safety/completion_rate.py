#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from typing import Any

from mce.core.metric import Metric, MetricRequirements, MetricResult
from mce.core.specs import SpecRegistry
from mce.providers.native.metrics.safety.execution_error_support import (
    derive_session_completion,
)


def _session_completion_from_context(context: dict[str, Any]) -> bool:
    session = context.get("session") or {}
    explicit = context.get("completion", session.get("completion"))
    if explicit is not None:
        return bool(explicit)

    llm_spans = context.get("llm_spans", [])
    tool_spans = context.get("tool_spans", [])
    return derive_session_completion(llm_spans, tool_spans)


class CompletionRate(Metric):
    """Computes completion as a per-session boolean or a mean across sessions."""

    metadata = SpecRegistry.require("CompletionRate").metadata

    @property
    def input_requirements(self) -> MetricRequirements:
        return SpecRegistry.require("CompletionRate").input_requirements

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        sessions = context.get("sessions") or context.get("session_set")
        if isinstance(sessions, list) and sessions:
            completions = []
            for session_context in sessions:
                if isinstance(session_context, dict):
                    completions.append(
                        1.0
                        if _session_completion_from_context(session_context)
                        else 0.0
                    )
                else:
                    completions.append(
                        1.0
                        if bool(getattr(session_context, "completion", True))
                        else 0.0
                    )

            completed = sum(completions)
            total = len(completions)
            value = completed / total if total else 0.0
            failed = total - int(completed)
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                provider="Native",
                value=value,
                metric_class=self.ontology_class,
                reasoning=f"1 - ({failed}/{total}) = {value:.4f}",
                metadata={"session_count": total, "failed_sessions": failed},
            )

        completed = _session_completion_from_context(context)
        return MetricResult(
            metric_id=self.metric_id,
            resource_id=resource_id,
            provider="Native",
            value=1.0 if completed else 0.0,
            metric_class=self.ontology_class,
            reasoning="Session completed." if completed else "Session failed.",
            metadata={"completion": completed},
        )
