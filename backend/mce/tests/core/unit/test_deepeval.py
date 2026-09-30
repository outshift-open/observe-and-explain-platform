#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.deepeval provider and wrapper."""

import sys
import pytest
from unittest.mock import MagicMock, patch

# ============================================================================
# Module-level deepeval mock (deepeval is not installed in test env)
# ============================================================================

_DEEPEVAL_MOCK = MagicMock()
_DEEPEVAL_TC_MOCK = MagicMock()


def _inject_deepeval_mocks():
    """Inject deepeval into sys.modules so imports succeed."""
    sys.modules.setdefault("deepeval", _DEEPEVAL_MOCK)
    sys.modules.setdefault("deepeval.models", MagicMock())
    sys.modules.setdefault("deepeval.test_case", _DEEPEVAL_TC_MOCK)
    sys.modules.setdefault("deepeval.metrics", MagicMock())


_inject_deepeval_mocks()


# ============================================================================
# DeepEvalProvider
# ============================================================================


class TestDeepEvalProvider:
    def setup_method(self):
        from mce.providers.deepeval.provider import DeepEvalProvider

        self.Provider = DeepEvalProvider

    def test_init_default_uses_env_model(self, monkeypatch):
        monkeypatch.setenv("LLM_MODEL_NAME", "gpt-3.5")
        prov = self.Provider()
        assert prov._model_config == "gpt-3.5"
        assert prov._model_instance is None

    def test_init_explicit_string_model(self):
        prov = self.Provider(model="claude-3")
        assert prov._model_config == "claude-3"
        assert prov._model_instance is None

    def test_init_with_object_model(self):
        mock_model = MagicMock()
        prov = self.Provider(model=mock_model)
        assert prov._model_instance is mock_model

    def test_model_property_lazy_creates_adapter(self):
        prov = self.Provider(model="gpt-4")
        mock_adapter = MagicMock()
        mock_adapter_cls = MagicMock(return_value=mock_adapter)
        with patch(
            "mce.providers.deepeval.provider._get_adapter_class",
            return_value=mock_adapter_cls,
        ):
            result = prov.model
        assert result is mock_adapter
        mock_adapter_cls.assert_called_once_with("gpt-4")

    def test_model_property_caches_instance(self):
        prov = self.Provider(model="gpt-4")
        mock_adapter = MagicMock()
        with patch(
            "mce.providers.deepeval.provider._get_adapter_class",
            return_value=MagicMock(return_value=mock_adapter),
        ):
            r1 = prov.model
            r2 = prov.model
        assert r1 is r2  # Same instance on second call

    def test_model_property_object_model_returned_directly(self):
        mock_model = MagicMock()
        mock_model.__class__ = object  # not str
        prov = self.Provider(model=mock_model)
        assert prov.model is mock_model

    def test_set_model_string_clears_instance(self):
        prov = self.Provider(model="gpt-4")
        prov._model_instance = MagicMock()
        prov.set_model("claude-3")
        assert prov._model_instance is None
        assert prov._model_config == "claude-3"
        assert prov._instances == {}

    def test_set_model_object_sets_instance(self):
        prov = self.Provider()
        obj = MagicMock()
        prov.set_model(obj)
        assert prov._model_instance is obj
        assert prov._instances == {}

    def test_getstate_clears_instance(self):
        prov = self.Provider(model="gpt-4")
        prov._model_instance = MagicMock()
        state = prov.__getstate__()
        assert state["_model_instance"] is None
        assert state["_instances"] == {}

    def test_setstate_restores(self):
        prov = self.Provider()
        state = {"_model_config": "gpt-4", "_model_instance": None, "_instances": {}}
        prov.__setstate__(state)
        assert prov._model_config == "gpt-4"

    def test_get_metric_not_in_factory_returns_none(self):
        prov = self.Provider(model="gpt-4")
        with patch(
            "mce.providers.deepeval.metrics_factory.get_metric_factory", return_value={}
        ):
            result = prov.get_metric("NonExistentMetric")
        assert result is None

    def test_get_metric_factory_exception_returns_none(self):
        prov = self.Provider(model="gpt-4")
        with patch(
            "mce.providers.deepeval.metrics_factory.get_metric_factory",
            side_effect=Exception("boom"),
        ):
            result = prov.get_metric("AnswerRelevancy")
        assert result is None

    def test_get_metric_found_creates_instance(self):
        prov = self.Provider(model="gpt-4")
        mock_metric = MagicMock()
        mock_factory_fn = MagicMock(return_value=mock_metric)
        with patch(
            "mce.providers.deepeval.metrics_factory.get_metric_factory",
            return_value={"AnswerRelevancy": mock_factory_fn},
        ):
            mock_model = MagicMock()
            with patch.object(
                type(prov),
                "model",
                new_callable=lambda: property(lambda self: mock_model),
            ):
                result = prov.get_metric("AnswerRelevancy")
        assert result is mock_metric

    def test_build_test_case_deepeval_not_installed(self):
        prov = self.Provider()
        # Remove mocked deepeval.test_case temporarily
        saved = sys.modules.pop("deepeval.test_case", None)
        sys.modules["deepeval.test_case"] = None
        try:
            result = prov.build_test_case({"input_text": "Q", "output_text": "A"})
            assert result is None
        finally:
            if saved is not None:
                sys.modules["deepeval.test_case"] = saved

    def test_build_test_case_with_mock_tc(self):
        prov = self.Provider()
        mock_tc = MagicMock()
        mock_tc_cls = MagicMock(return_value=mock_tc)
        with patch("deepeval.test_case.LLMTestCase", mock_tc_cls):
            prov.build_test_case(
                {
                    "input_text": "What is Python?",
                    "output_text": "A language",
                    "expected_output": "Python is a language",
                    "retrieval_context": ["doc1"],
                }
            )
        mock_tc_cls.assert_called_once()

    def test_build_test_case_alternate_input_keys(self):
        prov = self.Provider()
        mock_tc = MagicMock()
        mock_tc_cls = MagicMock(return_value=mock_tc)
        with patch("deepeval.test_case.LLMTestCase", mock_tc_cls):
            prov.build_test_case(
                {
                    "input_query": "Q",
                    "final_response": "A",
                    "context": ["ctx"],
                }
            )
        mock_tc_cls.assert_called_once()
        call_kwargs = mock_tc_cls.call_args[1]
        assert call_kwargs["input"] == "Q"
        assert call_kwargs["actual_output"] == "A"

    def test_build_test_case_from_kg_native_fields(self):
        prov = self.Provider()
        mock_tc_cls = MagicMock(return_value=MagicMock())
        with patch("deepeval.test_case.LLMTestCase", mock_tc_cls):
            prov.build_test_case(
                {
                    "conversation_data": {"query": "Q", "response": "A"},
                    "llm_spans": [
                        {"inputContent": "Q"},
                        {"outputContent": "A"},
                    ],
                }
            )
        call_kwargs = mock_tc_cls.call_args[1]
        assert call_kwargs["input"] == "Q"
        assert call_kwargs["actual_output"] == "A"

    def test_build_test_case_non_list_context_converted(self):
        prov = self.Provider()
        mock_tc_cls = MagicMock(return_value=MagicMock())
        with patch("deepeval.test_case.LLMTestCase", mock_tc_cls):
            prov.build_test_case(
                {
                    "input_text": "Q",
                    "output_text": "A",
                    "retrieval_context": "single string",
                }
            )
        call_kwargs = mock_tc_cls.call_args[1]
        assert isinstance(call_kwargs["retrieval_context"], list)

    def test_evaluate_unavailable_metric_returns_default(self):
        prov = self.Provider(model="gpt-4")
        with patch.object(prov, "get_metric", return_value=None):
            result = prov.evaluate("AnswerRelevancy", {})
        assert result["score"] == 0.0

    def test_evaluate_unavailable_test_case_returns_default(self):
        prov = self.Provider(model="gpt-4")
        mock_metric = MagicMock()
        with patch.object(prov, "get_metric", return_value=mock_metric):
            with patch.object(prov, "build_test_case", return_value=None):
                result = prov.evaluate("AnswerRelevancy", {})
        assert result["score"] == 0.0

    def test_evaluate_success(self):
        prov = self.Provider(model="gpt-4")
        mock_metric = MagicMock()
        mock_tc = MagicMock()
        with patch.object(prov, "get_metric", return_value=mock_metric):
            with patch.object(prov, "build_test_case", return_value=mock_tc):
                with patch.object(
                    prov,
                    "_measure_sync_wrapper",
                    return_value={"score": 0.9, "reasoning": "good"},
                ):
                    result = prov.evaluate("AnswerRelevancy", {})
        assert result["score"] == pytest.approx(0.9)

    def test_evaluate_exception_returns_error(self):
        prov = self.Provider(model="gpt-4")
        mock_metric = MagicMock()
        mock_tc = MagicMock()
        with patch.object(prov, "get_metric", return_value=mock_metric):
            with patch.object(prov, "build_test_case", return_value=mock_tc):
                with patch.object(
                    prov, "_measure_sync_wrapper", side_effect=Exception("fail")
                ):
                    result = prov.evaluate("AnswerRelevancy", {})
        assert result["score"] == 0.0

    def test_measure_sync_wrapper(self):
        prov = self.Provider()
        mock_metric = MagicMock()
        mock_metric.score = 0.77
        mock_metric.reason = "because"
        mock_tc = MagicMock()
        with patch.dict("sys.modules", {"nest_asyncio": MagicMock()}):
            result = prov._measure_sync_wrapper(mock_metric, mock_tc)
        mock_metric.measure.assert_called_once_with(mock_tc)
        assert result["score"] == pytest.approx(0.77)
        assert result["reasoning"] == "because"


# ============================================================================
# DeepEvalMetricWrapper
# ============================================================================


class TestDeepEvalMetricWrapper:
    def _make_wrapper(
        self,
        metric_name="AnswerRelevancy",
        aggregation="execution_element",
        provider=None,
    ):
        from mce.providers.deepeval.wrapper import DeepEvalMetricWrapper

        config = {"requirements": {"aggregation_level": aggregation}}
        return DeepEvalMetricWrapper(metric_name, config, provider=provider)

    def test_init_execution_element_scope(self):
        from mce.core.metric import MetricScope

        w = self._make_wrapper(aggregation="execution_element")
        assert w.metadata.scope == MetricScope.EXECUTION_ELEMENT

    def test_init_session_scope(self):
        from mce.core.metric import MetricScope

        w = self._make_wrapper(aggregation="session")
        assert w.metadata.scope == MetricScope.SESSION

    def test_check_availability_deepeval_missing(self):
        w = self._make_wrapper()
        with patch("importlib.util.find_spec", return_value=None):
            w._check_availability()
        assert w._availability_status is False

    def test_check_availability_deepeval_present(self):
        w = self._make_wrapper()
        w._availability_status = True  # reset
        mock_spec = MagicMock()
        with patch("importlib.util.find_spec", return_value=mock_spec):
            w._check_availability()
        assert w._availability_status is True

    def test_check_availability_value_error_skipped(self):
        w = self._make_wrapper()
        with patch("importlib.util.find_spec", side_effect=ValueError("mocked")):
            w._check_availability()  # Must NOT raise

    def test_init_with_model(self):
        w = self._make_wrapper()
        mock_model = MagicMock()
        mock_prov = MagicMock()
        w._provider = mock_prov
        w.init_with_model(mock_model)
        assert w._model is mock_model
        mock_prov.set_model.assert_called_once_with(mock_model)

    def test_call_external_sync(self):
        w = self._make_wrapper()
        mock_prov = MagicMock()
        mock_prov.evaluate.return_value = {"score": 0.8, "reasoning": "ok"}
        w._provider = mock_prov
        w.call_external_sync(input_text="Q", output_text="A")
        mock_prov.evaluate.assert_called_once_with(
            "AnswerRelevancy", {"input_text": "Q", "output_text": "A"}
        )

    def test_get_provider_returns_existing(self):
        w = self._make_wrapper()
        mock_prov = MagicMock()
        w._provider = mock_prov
        assert w._get_provider() is mock_prov

    def test_get_provider_lazy_init(self):
        w = self._make_wrapper()
        w._provider = None
        prov = w._get_provider()
        assert prov is not None

    def test_compute_batch_empty_returns_empty(self):
        w = self._make_wrapper()
        result = w.compute_batch([], [])
        assert result == []
