#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any
import logging
import os
import sys
import warnings
from mce.core.helpers import _query_response

logger = logging.getLogger(__name__)

# Opt out of DeepEval telemetry before the package is ever imported.
# deepeval/telemetry.py runs side-effectful code at import time (creates
# .deepeval/.deepeval_telemetry.txt and sends events to PostHog/Sentry).
# Setting this env var here, at module load, ensures the flag is present
# even when deepeval is already cached in sys.modules from a previous import.
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

# Lazy loading mechanism for MCEDeepEvalAdapter to avoid top-level import of deepeval
_AdapterClass = None


def _get_adapter_class():
    global _AdapterClass
    if _AdapterClass:
        return _AdapterClass

    # Warn if using Python 3.14+ (DeepEval has known asyncio.timeout() issues)
    if sys.version_info >= (3, 14):
        warnings.warn(
            "DeepEval provider is not fully compatible with Python 3.14+ due to "
            "asyncio.timeout() behavior changes. Some metrics may fail. "
            "Consider: (1) Use Python <3.14, or (2) Disable DeepEval via MCE_ENABLE_DEEPEVAL=false",
            RuntimeWarning,
            stacklevel=2,
        )

    try:
        from deepeval.models import DeepEvalBaseLLM

        # If deepeval was already loaded before the env var was set, patch the
        # settings singleton so telemetry is disabled at the object level too.
        try:
            from deepeval.config.settings import get_settings

            get_settings().DEEPEVAL_TELEMETRY_OPT_OUT = True
        except Exception:
            pass
    except ImportError:

        class DeepEvalBaseLLM:
            pass

    class MCEDeepEvalAdapter(DeepEvalBaseLLM):
        """
        Adapts MCE's caching LLMClient to DeepEval's BaseLLM interface.
        Ensures all DeepEval LLM calls go through our cache/record system.
        """

        def __init__(self, model_name: str):
            self.model_name = model_name
            self._client = None

        def load_model(self):
            from mce.engine.llm import LLMService

            self._client = LLMService.get_instance()
            return self._client

        def generate(self, prompt: str) -> str:
            logger.debug(
                "MCEDeepEvalAdapter.generate called for model %s", self.model_name
            )
            if not self._client:
                self.load_model()
            return self._client.get_completion(prompt, model=self.model_name)

        async def a_generate(self, prompt: str) -> str:
            logger.debug(
                "MCEDeepEvalAdapter.a_generate called for model %s", self.model_name
            )
            if not self._client:
                self.load_model()
            # Wrap sync MCE client in thread to satisfy async interface
            import asyncio

            return await asyncio.to_thread(
                self._client.get_completion, prompt, model=self.model_name
            )

        def get_model_name(self):
            return self.model_name

    _AdapterClass = MCEDeepEvalAdapter
    return _AdapterClass


# Shared DeepEval provider that owns model state and conversion logic.


class DeepEvalProvider:
    def __init__(self, model: Any = None):
        # We store model configuration lazily to avoid triggering heavy imports (deepeval, torch) at startup
        self._model_instance = None
        self._instances: dict[str, Any] = {}

        if model is None:
            # Store the model name for lazy initialization
            self._model_config = (
                os.getenv("MCE_LLM_MODEL") or os.getenv("LLM_MODEL_NAME") or "gpt-4o"
            )
        else:
            self._model_config = model

        # If user passed an already instantiated object (not string), use it immediately
        if not isinstance(self._model_config, str):
            self._model_instance = self._model_config

    @property
    def model(self):
        """Lazy property to get the configured model/adapter."""
        if self._model_instance is not None:
            return self._model_instance

        # Re-hydrate if we have config (handling case where config is an object)
        if not isinstance(self._model_config, str):
            self._model_instance = self._model_config
            return self._model_instance

        # Initialize adapter from string
        Adapter = _get_adapter_class()
        self._model_instance = Adapter(self._model_config)
        return self._model_instance

    def __getstate__(self):
        state = self.__dict__.copy()
        # Don't pickle the runtime adapter instance to avoid pickling local classes
        # and to ensure fresh connections on restore.
        state["_model_instance"] = None
        state["_instances"] = {}  # Clear cache
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        # _model_instance is None, will be lazy loaded on access via property

    def set_model(self, model: Any) -> None:
        self._model_config = model
        if isinstance(model, str):
            self._model_instance = None  # Will be re-created on next access
        else:
            self._model_instance = model
        self._instances = {}

    def get_metric(self, metric_name: str) -> Any | None:
        """
        Get a configured DeepEval metric instance by name.

        Uses metrics_factory to simplify metric instantiation logic.
        Creates a new instance for every evaluation to support concurrency
        (DeepEval metrics are stateful and store results in self.score).

        Args:
            metric_name: Name of the DeepEval metric (e.g. 'AnswerRelevancy', 'Bias')

        Returns:
            Configured DeepEval metric instance, or None if unavailable
        """
        try:
            from .metrics_factory import get_metric_factory

            factory_registry = get_metric_factory()

            if metric_name in factory_registry:
                model_instance = self.model  # Triggers lazy loading
                return factory_registry[metric_name](model_instance)
            else:
                return None
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(
                f"Failed to create DeepEval metric {metric_name}: {e}"
            )
            return None

    def build_test_case(self, context: dict[str, Any]) -> Any | None:
        try:
            from deepeval.test_case import LLMTestCase
        except ImportError:
            return None

        input_text, output_text = _query_response(context)
        input_text = input_text or context.get("input") or ""
        output_text = output_text or context.get("output") or ""
        expected_output = context.get("expected_output") or context.get("ground_truth")
        retrieval_context = (
            context.get("context")
            or context.get("retrieval_context")
            or context.get("retrieved_context")
            or []
        )
        if not isinstance(retrieval_context, list):
            retrieval_context = [str(retrieval_context)]

        return LLMTestCase(
            input=input_text,
            actual_output=output_text,
            expected_output=expected_output,
            retrieval_context=retrieval_context,
        )

    def evaluate(self, metric_name: str, context: dict[str, Any]) -> dict[str, Any]:
        import time

        start_t = time.time()
        metric = self.get_metric(metric_name)
        if metric is None:
            return {"score": 0.0, "reasoning": "DeepEval metric unavailable."}

        test_case = self.build_test_case(context)
        if test_case is None:
            return {"score": 0.0, "reasoning": "DeepEval test case unavailable."}

        prep_t = time.time() - start_t
        # Run measurement (async or sync based on library support)
        # Most DeepEval metrics are synchronous in their measure() but use async LLM calls internally
        # We wrap in thread pool to avoid blocking the main loop
        try:
            import concurrent.futures

            logger.debug("DeepEval evaluate %s with max_workers=16", metric_name)
            with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
                measure_start = time.time()
                future = executor.submit(self._measure_sync_wrapper, metric, test_case)
                result = future.result(timeout=120)
                measure_duration = time.time() - measure_start
                logger.debug(
                    "DeepEval %s took %.2fs (prep: %.4fs)",
                    metric_name,
                    measure_duration,
                    prep_t,
                )
                return result
        except Exception as e:
            return {"score": 0.0, "reasoning": f"DeepEval error: {str(e)}"}

    def _measure_sync_wrapper(self, metric, test_case):
        """
        Helper to run metric.measure() in a thread.
        Handles nested async loops if needed via nest_asyncio.
        """
        try:
            import nest_asyncio

            nest_asyncio.apply()
        except ImportError:
            pass

        metric.measure(test_case)
        return {
            "score": getattr(metric, "score", 0.0),
            "reasoning": getattr(metric, "reason", ""),
        }
