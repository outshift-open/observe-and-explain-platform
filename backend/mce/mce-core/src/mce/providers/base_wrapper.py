#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
from mce.core.types import MetricResult
from mce.core.metric import Metric, MetricRequirements
from mce.core.metadata import MetricMetadata, MetricLayer, MetricNature, MetricScope


class ExternalMetricWrapper(Metric):
    """
    Generic wrapper for external metrics (DeepEval, Opik, Ragas)
    that fits into MCE v2 Architecture.
    """

    def __init__(
        self,
        metric_name: str,
        config: dict[str, Any],
        provider_name: str,
        scope: MetricScope = MetricScope.EXECUTION_ELEMENT,
    ):
        self._metric_name = metric_name
        self._config = config
        self._provider_name = provider_name

        # Lazy load requirements from config
        self._reqs = config.get("requirements", {})

        # v2 Metadata Initialization
        self.metadata = MetricMetadata(
            name=metric_name,
            description=f"{provider_name} wrapper for {metric_name}",
            layer=MetricLayer.GOVERNANCE,  # Defaulting to Governance for external evaluators
            nature=MetricNature.STOCHASTIC,  # Assuming LLM-based
            scope=scope,
            ontology_class=metric_name,
            attachment_point=self._reqs.get(
                "attachment_point"
            ),  # Load from config if present
            provider=provider_name,  # Fix #2: populate metadata.provider for get_provider_name()
        )

        self._instance = None
        self._model = None

        self._availability_status: bool = True
        self._availability_error: str | None = None

        # Perform check
        self._check_availability()

    def _check_availability(self):
        """Override to implement dependency checks."""
        pass

    @property
    def is_available(self) -> bool:
        return self._availability_status

    @property
    def input_requirements(self) -> MetricRequirements:
        params = self._reqs.get("required_input_parameters", [])
        return MetricRequirements(text_fields=params)

    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        """
        Standard execution flow:
        1. Parse context (inputs/outputs/context)
        2. Call external synchronous method (subclass implemented)
        3. Wrap result
        """
        if not self.is_available:
            return MetricResult(
                metric_id=self.metadata.name,
                resource_id=resource_id,
                provider=self._provider_name,
                value=0.0,
                error=f"Provider Unavailable: {self._availability_error}",
            )

        try:
            # Filter internal engine dependency-tracking keys ("metric:*") before
            # spreading into kwargs — they are not part of any public API and would
            # cause unexpected-keyword-argument errors in external provider methods.
            filtered_ctx = {
                k: v for k, v in context.items() if not k.startswith("metric:")
            }

            # Subclass hook
            result = self.call_external_sync(**filtered_ctx)

            # Result normalization
            val = 0.0
            reason = ""
            if isinstance(result, dict):
                val = result.get("score", 0.0)
                reason = result.get("reasoning", "")
            elif hasattr(result, "score"):
                val = result.score
                reason = getattr(result, "reason", "") or getattr(
                    result, "reasoning", ""
                )
            elif isinstance(result, (float, int)):
                val = float(result)

            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                value=val,
                reasoning=reason,
                provider=self._provider_name,
                metric_class=self.ontology_class,
                metadata={
                    "scope": self.scope.value
                },  # Fix #1: removed self.domain (undefined)
            )
        except NotImplementedError:
            raise  # Stub not implemented — propagate so callers discover missing impls
        except Exception as e:
            return MetricResult(
                metric_id=self.metric_id,
                resource_id=resource_id,
                value=0.0,
                reasoning=f"Compute Error: {str(e)}",
                provider=self._provider_name,
                metric_class=self.ontology_class,
                error=str(e),
            )

    def call_external_sync(self, **kwargs) -> Any:
        """Override in subclasses to invoke specific library logic."""
        raise NotImplementedError("Subclasses must implement call_external_sync")
