#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
import logging
from mce.core.metric import MetricScope
from ..base_wrapper import ExternalMetricWrapper
from .provider import DeepEvalProvider

logger = logging.getLogger(__name__)


class DeepEvalMetricWrapper(ExternalMetricWrapper):
    """
    Wrapper for DeepEval metrics to fit into MCE v2 Architecture.
    """

    def __init__(
        self,
        metric_name: str,
        config: dict[str, Any],
        provider: DeepEvalProvider = None,
    ):
        agg = config.get("requirements", {}).get(
            "aggregation_level", "execution_element"
        )

        scope = MetricScope.EXECUTION_ELEMENT
        if agg == "session":
            scope = MetricScope.SESSION
        elif agg == "span":
            scope = MetricScope.EXECUTION_ELEMENT

        super().__init__(metric_name, config, "DeepEval", scope)
        self._provider = provider

    def _check_availability(self):
        import importlib.util

        try:
            if importlib.util.find_spec("deepeval") is None:
                self._availability_status = False
                self._availability_error = "deepeval package not found"
        except (ValueError, AttributeError):
            # Raised when sys.modules["deepeval"] is a MagicMock without __spec__ set
            # (e.g. in unit tests that pre-mock the module).  Treat as available.
            pass

    def init_with_model(self, model: Any):
        """Inject LLM Config"""
        self._model = model
        self._get_provider().set_model(model)

    def call_external_sync(self, **kwargs) -> Any:
        """Translate MCE context -> DeepEval LLMTestCase -> score."""
        return self._get_provider().evaluate(self._metric_name, kwargs)

    def _get_provider(self) -> DeepEvalProvider:
        # Lazy-init to keep listing fast and avoid heavy dependency imports.
        if self._provider is None:
            self._provider = DeepEvalProvider()
            if self._model is not None:
                self._provider.set_model(self._model)
        return self._provider

    def compute_batch(self, resources: list, contexts: list) -> list:
        """
        Parallel execution for DeepEval metrics using ThreadPool.
        Overrides default sequential implementation.
        """
        from mce.core.metric import MetricResult
        import concurrent.futures

        # Fast path for empty
        if not resources:
            return []

        # We use the provider's internal parallelism where possible, or wrap here.
        # Since call_external_sync is the entry point, we parallelize calls to it.

        results = [None] * len(resources)

        import os

        # Helper to run one item and capture index
        def _process_item(idx, rid, ctx):
            try:
                # Same logic as base.compute() but simplified
                return self.compute(rid, ctx)
            except Exception as e:
                return MetricResult(
                    metric_id=self.metric_id,
                    resource_id=rid,
                    provider="DeepEval",
                    value=0.0,
                    error=str(e),
                    reasoning=f"Batch Exec Failed: {e}",
                )

        # Use a pool sized from env (MCE_DEEPEVAL_MAX_WORKERS) or default 4.
        max_workers = int(os.environ.get("MCE_DEEPEVAL_MAX_WORKERS", "4"))
        logger.info(
            f"[DeepEval] Starting parallel batch execution for {len(resources)} items (max_workers={max_workers})"
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_process_item, i, r, c): i
                for i, (r, c) in enumerate(zip(resources, contexts))
            }

            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    # Should be caught inside _process_item, but just in case
                    results[idx] = MetricResult(
                        metric_id=self.metric_id,
                        resource_id=resources[idx],
                        provider="DeepEval",
                        error=str(e),
                    )

        return results
