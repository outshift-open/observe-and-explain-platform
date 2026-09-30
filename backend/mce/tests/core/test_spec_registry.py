#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.core.specs — MetricSpec and SpecRegistry."""

import pytest
from mce.core.specs import MetricSpec, SpecRegistry
from mce.core.metadata import MetricLayer, MetricNature, MetricScope
from mce.core.metric import MetricRequirements


@pytest.fixture(autouse=True)
def reset_registry():
    """Ensure a clean SpecRegistry state for every test."""
    SpecRegistry._reset()
    yield
    SpecRegistry._reset()


# ---------------------------------------------------------------------------
# MetricSpec
# ---------------------------------------------------------------------------


class TestMetricSpec:
    def test_minimal_spec_creation(self):
        spec = MetricSpec(
            name="TestMetric",
            description="A test metric.",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.DETERMINISTIC,
            scope=MetricScope.SESSION,
            ontology_class="TestMetric",
        )
        assert spec.name == "TestMetric"
        assert spec.version == "1.0.0"
        assert spec.tags == ()
        assert spec.input_requirements.text_fields == []

    def test_spec_with_requirements(self):
        spec = MetricSpec(
            name="AnswerRelevancy",
            description="desc",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.STOCHASTIC,
            scope=MetricScope.SESSION,
            ontology_class="AnswerRelevancy",
            input_requirements=MetricRequirements(
                text_fields=["conversation_text", "transcript"]
            ),
        )
        assert "conversation_text" in spec.input_requirements.text_fields

    def test_to_dict_contains_required_keys(self):
        spec = MetricSpec(
            name="Bias",
            description="Bias metric",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.STOCHASTIC,
            scope=MetricScope.SESSION,
            ontology_class="Bias",
        )
        d = spec.to_dict()
        assert d["id"] == "Bias"
        assert d["layer"] == "Execution"
        assert d["nature"] == "Stochastic"
        assert d["scope"] == "Session"
        assert "input_requirements" in d
        assert isinstance(d["tags"], list)

    def test_spec_tags_tuple(self):
        spec = MetricSpec(
            name="X",
            description="x",
            layer=MetricLayer.EXECUTION,
            nature=MetricNature.DETERMINISTIC,
            scope=MetricScope.SESSION,
            ontology_class="X",
            tags=("safety", "governance"),
        )
        assert "safety" in spec.tags


# ---------------------------------------------------------------------------
# SpecRegistry
# ---------------------------------------------------------------------------


class TestSpecRegistry:
    def test_discovers_all_builtin_specs(self):
        specs = SpecRegistry.all_specs()
        # We ship 34 spec files — guard against accidental deletions
        assert len(specs) >= 34

    def test_all_specs_are_sorted_alphabetically(self):
        specs = SpecRegistry.all_specs()
        names = [s.name for s in specs]
        assert names == sorted(names)

    def test_get_known_spec(self):
        spec = SpecRegistry.get("AnswerRelevancy")
        assert spec is not None
        assert spec.name == "AnswerRelevancy"
        assert spec.nature == MetricNature.STOCHASTIC

    def test_get_unknown_returns_none(self):
        assert SpecRegistry.get("NonExistentMetric9999") is None

    def test_count_matches_all_specs(self):
        assert SpecRegistry.count() == len(SpecRegistry.all_specs())

    def test_session_scope_specs(self):
        session_specs = [
            s for s in SpecRegistry.all_specs() if s.scope == MetricScope.SESSION
        ]
        assert len(session_specs) >= 20  # majority are session-scoped

    def test_execution_element_scope_specs(self):
        ee_specs = [
            s
            for s in SpecRegistry.all_specs()
            if s.scope == MetricScope.EXECUTION_ELEMENT
        ]
        names = {s.name for s in ee_specs}
        assert "Hallucination" in names
        assert "Sentiment" in names
        assert "ToolError" in names

    def test_deterministic_specs(self):
        det = [
            s
            for s in SpecRegistry.all_specs()
            if s.nature == MetricNature.DETERMINISTIC
        ]
        names = {s.name for s in det}
        assert "AgentToAgentInteractions" in names
        assert "WorkflowEfficiency" in names
        assert "ToolError" in names

    def test_all_specs_have_ontology_class(self):
        for spec in SpecRegistry.all_specs():
            assert spec.ontology_class, f"{spec.name} has no ontology_class"

    def test_all_specs_have_description(self):
        for spec in SpecRegistry.all_specs():
            assert spec.description.strip(), f"{spec.name} has empty description"

    def test_reset_clears_state(self):
        SpecRegistry.all_specs()  # trigger discovery
        assert SpecRegistry.count() > 0
        SpecRegistry._reset()
        assert SpecRegistry._discovered is False
        assert len(SpecRegistry._specs) == 0

    def test_idempotent_discovery(self):
        """Calling all_specs() multiple times should return the same count."""
        count1 = SpecRegistry.count()
        count2 = SpecRegistry.count()
        assert count1 == count2

    def test_specific_spec_input_requirements(self):
        spec = SpecRegistry.get("ToolUtilizationAccuracy")
        assert spec is not None
        assert "tool_definition" in spec.input_requirements.text_fields
        assert "toolName" in spec.input_requirements.text_fields

    def test_graph_determinism_no_inputs(self):
        spec = SpecRegistry.get("GraphDeterminismScore")
        assert spec is not None
        assert spec.input_requirements.text_fields == []

    def test_hallucination_scope(self):
        spec = SpecRegistry.get("Hallucination")
        assert spec is not None
        assert spec.scope == MetricScope.EXECUTION_ELEMENT
        assert "context" in spec.input_requirements.text_fields
