#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
import logging
from .types import MetricResult
from .metadata import (
    MetricMetadata,
    MetricLayer,
    MetricNature,
    MetricScope,
    MetricRequirements,
)

logger = logging.getLogger(__name__)


class Metric(ABC):
    """
    Base interface for all MCE v2 Metrics (Plugins).
    Defines the contract for Identity, Ontology, and Computation.
    """

    # Subclasses must assign self.metadata = MetricMetadata(...) in __init__.
    # Declared as a class-level annotation so type-checkers can verify it;
    # __getattr__ below provides a clear error if a subclass forgets.
    metadata: MetricMetadata

    def __getattr__(self, name: str):
        """Provide a helpful error when a subclass forgets to set self.metadata."""
        if name == "metadata":
            raise AttributeError(
                f"{type(self).__name__} must assign "
                "'self.metadata = MetricMetadata(...)' in __init__."
            )
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    @property
    def metric_id(self) -> str:
        """Proxies to metadata."""
        return self.metadata.name

    @property
    def ontology_class(self) -> str:
        """Proxies to metadata."""
        return self.metadata.ontology_class

    @property
    def domain(self) -> MetricLayer:
        """Proxies to metadata."""
        return self.metadata.layer

    @property
    def nature(self) -> MetricNature:
        """Proxies to metadata."""
        return self.metadata.nature

    @property
    def scope(self) -> MetricScope:
        """Proxies to metadata."""
        return self.metadata.scope

    @property
    def dependencies(self) -> list[str]:
        """Proxies to metadata."""
        return self.metadata.dependencies

    @property
    def is_virtual(self) -> bool:
        """True if this metric derives from other metrics (aggregate/transform).
        Virtual metrics are never cached: their values depend entirely on base
        metric results and must be recomputed each time."""
        return False

    @property
    def input_requirements(self) -> MetricRequirements:
        """
        Data required to compute this metric.
        This remains overrideable logic, as it might depend on config.
        """
        return MetricRequirements()

    @abstractmethod
    def compute(self, resource_id: str, context: dict[str, Any]) -> MetricResult:
        """
        Compute the metric.

        Args:
            resource_id: The ID of the thing being measured.
            context: Data bundle satisfying input_requirements.
        """
        pass

    def compute_batch(
        self, resources: list[str], contexts: list[dict[str, Any]]
    ) -> list[MetricResult]:
        """
        Compute metric for a batch of resources.
        Default implementation iterates compute(). Override for optimization.
        """
        results = []
        for rid, ctx in zip(resources, contexts):
            try:
                results.append(self.compute(rid, ctx))
            except Exception as e:
                # Log with traceback so programming errors are visible in DEBUG mode;
                # then capture as an error result rather than stopping the batch.
                logger.exception(
                    "compute() raised on metric=%s resource=%s", self.metric_id, rid
                )
                results.append(
                    MetricResult(
                        metric_id=self.metric_id,
                        resource_id=rid,
                        provider="System",
                        value=0.0,
                        metric_class=self.ontology_class,
                        error=str(e),
                        reasoning=f"Execution Failed: {str(e)}",
                    )
                )
        return results

    def call_llm(self, prompt: str) -> str:
        """
        Call LLM using the centralized LLMService.
        Propagates exceptions so callers receive clear failures rather than
        silent garbage scores.
        """
        from mce.engine.llm import LLMService

        service = LLMService.get_instance()
        return service.get_completion(prompt)
