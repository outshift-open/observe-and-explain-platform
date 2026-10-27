# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for oxp-ontology package
"""

from pathlib import Path

import pytest

from oxp_ontology import (
    ONTOLOGY_FILES,
    __version__,
    get_ontology_path,
    load_graph,
    parse_version,
    validate_bundled_ontologies,
    validate_session_payload,
)


class TestOntologyPaths:
    """Test ontology file access"""

    def test_version_exists(self):
        """Package has a version"""
        assert __version__
        assert isinstance(__version__, str)

    def test_get_mas_ontology_path(self):
        """Can retrieve MAS ontology path"""
        path = get_ontology_path("mas")
        assert path.exists()
        assert path.name == "mas-ontology.ttl"
        assert path.is_file()

    def test_get_semantic_ontology_path(self):
        """Can retrieve semantic ontology path"""
        path = get_ontology_path("semantic")
        assert path.exists()
        assert path.name == "semantic-ontology.ttl"
        assert path.is_file()

    def test_get_metrics_ontology_path(self):
        """Can retrieve Metrics ontology path"""
        path = get_ontology_path("metrics")
        assert path.exists()
        assert path.name == "metrics-ontology.ttl"
        assert path.is_file()

    def test_get_ontology_with_extension(self):
        """Can retrieve ontology with .ttl extension"""
        path = get_ontology_path("mas-ontology.ttl")
        assert path.exists()
        assert path.name == "mas-ontology.ttl"

    def test_invalid_ontology_name(self):
        """Raises error for invalid ontology name"""
        with pytest.raises(FileNotFoundError):
            get_ontology_path("nonexistent")

    def test_all_declared_files_exist(self):
        """All files declared in ONTOLOGY_FILES exist"""
        for name, filename in ONTOLOGY_FILES.items():
            path = get_ontology_path(name)
            assert path.exists(), f"Missing file: {filename}"


class TestOntologyLoading:
    """Test ontology loading with rdflib"""

    def test_load_mas_ontology(self):
        """Can load MAS ontology into rdflib graph"""
        g = load_graph("mas")
        assert len(g) > 0, "Graph should contain triples"

    def test_load_semantic_ontology(self):
        """Can load semantic ontology into rdflib graph"""
        g = load_graph("semantic")
        assert len(g) > 0, "Graph should contain triples"

    def test_load_metrics_ontology(self):
        """Can load Metrics ontology into rdflib graph"""
        g = load_graph("metrics")
        assert len(g) > 0, "Graph should contain triples"


class TestOntologyValidity:
    """Validate TTL file syntax and structure"""

    @pytest.mark.parametrize("ontology_name", ["mas", "semantic", "metrics"])
    def test_ttl_parseable(self, ontology_name):
        """TTL file is syntactically valid"""
        from rdflib import Graph

        path = get_ontology_path(ontology_name)
        g = Graph()
        # Should not raise exception
        g.parse(path, format="turtle")
        assert len(g) > 0

    @pytest.mark.parametrize("ontology_name", ["mas", "semantic", "metrics"])
    def test_has_ontology_declaration(self, ontology_name):
        """Ontology has proper OWL Ontology declaration"""
        from rdflib import OWL, RDF, Graph

        g = Graph()
        path = get_ontology_path(ontology_name)
        g.parse(path, format="turtle")

        # Check for owl:Ontology declaration
        ontologies = list(g.subjects(RDF.type, OWL.Ontology))
        assert len(ontologies) > 0, f"No owl:Ontology found in {ontology_name}"

    @pytest.mark.parametrize("ontology_name", ["mas", "semantic", "metrics"])
    def test_has_classes(self, ontology_name):
        """Ontology defines at least one class"""
        from rdflib import OWL, RDF, Graph

        g = Graph()
        path = get_ontology_path(ontology_name)
        g.parse(path, format="turtle")

        classes = list(g.subjects(RDF.type, OWL.Class))
        assert len(classes) > 0, f"No owl:Class found in {ontology_name}"

    @pytest.mark.parametrize("ontology_name", ["mas", "semantic", "metrics"])
    def test_has_properties(self, ontology_name):
        """Ontology defines at least one property"""
        from rdflib import OWL, RDF, Graph

        g = Graph()
        path = get_ontology_path(ontology_name)
        g.parse(path, format="turtle")

        obj_props = list(g.subjects(RDF.type, OWL.ObjectProperty))
        data_props = list(g.subjects(RDF.type, OWL.DatatypeProperty))
        assert len(obj_props) + len(data_props) > 0, (
            f"No properties found in {ontology_name}"
        )

    def test_metrics_ontology_exposes_metric_result_contract(self):
        """Metrics ontology declares the Metric/MetricResult definition/observation split."""
        from rdflib import OWL, RDF, RDFS, Graph, Namespace

        g = Graph()
        path = get_ontology_path("metrics")
        g.parse(path, format="turtle")

        mas = Namespace("https://outshift-open.github.io/oxp-ontology/mas#")

        assert (mas.Metric, RDF.type, OWL.Class) in g
        assert (mas.Metric, RDFS.subClassOf, mas.Element) in g
        assert (mas.MetricResult, RDF.type, OWL.Class) in g
        assert (mas.MetricResult, RDFS.subClassOf, mas.Element) in g
        assert (mas.ofMetricType, RDF.type, OWL.ObjectProperty) in g
        assert (mas.ofMetricType, RDFS.domain, mas.MetricResult) in g
        assert (mas.ofMetricType, RDFS.range, mas.Metric) in g
        assert (mas.result, RDF.type, OWL.DatatypeProperty) in g
        assert (mas.reasoning, RDF.type, OWL.DatatypeProperty) in g

    def test_metric_result_declares_a_required_timestamp(self):
        """Every observation is timestamped, so results can be ordered over time."""
        from rdflib import RDFS, XSD, Graph, Namespace
        from rdflib.namespace import SH

        g = Graph()
        g.parse(get_ontology_path("metrics"), format="turtle")
        mas = Namespace("https://outshift-open.github.io/oxp-ontology/mas#")

        assert (mas.timestamp, RDFS.domain, mas.MetricResult) in g
        assert (mas.timestamp, RDFS.range, XSD.dateTime) in g
        assert next(g.objects(mas.timestamp, SH.minCount)).toPython() == 1

    def test_metric_result_declares_optional_evaluation_cost_properties(self):
        """LLM-judged metrics can record the judge model, its token usage and an estimated USD cost."""
        from rdflib import RDFS, XSD, Graph, Namespace
        from rdflib.namespace import SH

        g = Graph()
        g.parse(get_ontology_path("metrics"), format="turtle")
        mas = Namespace("https://outshift-open.github.io/oxp-ontology/mas#")

        expected = {
            "evaluationModel": XSD.string,
            "evaluationPromptTokenCount": XSD.integer,
            "evaluationCompletionTokenCount": XSD.integer,
            "evaluationTotalTokenCount": XSD.integer,
            "evaluationCost": XSD.double,
        }
        for name, datatype in expected.items():
            prop = mas[name]
            assert (prop, RDFS.domain, mas.MetricResult) in g, name
            assert (prop, RDFS.range, datatype) in g, name
            # optional: deterministic metrics make no LLM call
            assert (prop, SH.minCount, None) in g
            assert next(g.objects(prop, SH.minCount)).toPython() == 0, name

    def test_validation_library_accepts_rc_ordering(self):
        assert parse_version("1.0.0-rc0") < parse_version("1.0.0-rc1")
        assert parse_version("1.0.0-rc1") < parse_version("1.0.0")

    def test_validate_bundled_ontologies_returns_green_report(self):
        report = validate_bundled_ontologies()

        assert report.ok is True

    def test_validate_session_payload_flags_mismatched_span_session(self):
        report = validate_session_payload(
            {
                "session_id": "session-1",
                "session": {"sessionId": "session-1"},
                "agent_spans": [{"spanId": "span-1", "sessionId": "session-2"}],
                "llm_spans": [],
                "tool_spans": [],
                "conversation": [],
            }
        )

        assert report.ok is False
        assert "agent_spans[0] has mismatched sessionId" in report.issues


class TestCognitionProtocolReportsOntology:
    """The Cognition protocol reports and how metrics attach to them."""

    @staticmethod
    def _graph():
        from rdflib import Graph

        g = Graph()
        for name in ("mas", "metrics", "analysis"):
            g.parse(get_ontology_path(name), format="turtle")
        return g

    def test_report_classes_are_declared(self):
        from rdflib import OWL, RDF, RDFS, Namespace

        g, mas = (
            self._graph(),
            Namespace("https://outshift-open.github.io/oxp-ontology/mas#"),
        )
        for cls in (mas.CognitionProtocolReport, mas.CognitionProtocolExecutionReport):
            assert (cls, RDF.type, OWL.Class) in g
            assert (cls, RDFS.subClassOf, mas.Element) in g

    def test_reports_hang_off_a_session(self):
        from rdflib import RDFS, Namespace
        from rdflib.namespace import SH

        g, mas = (
            self._graph(),
            Namespace("https://outshift-open.github.io/oxp-ontology/mas#"),
        )
        assert (mas.reportsOn, RDFS.range, mas.Session) in g
        assert next(g.objects(mas.reportsOn, SH.minCount)).toPython() == 1

    def test_a_metric_result_can_measure_a_protocol_execution_report(self):
        from rdflib import OWL, RDFS, Namespace
        from rdflib.collection import Collection

        g, mas = (
            self._graph(),
            Namespace("https://outshift-open.github.io/oxp-ontology/mas#"),
        )
        union = next(g.objects(mas.measures, RDFS.range))
        members = set(Collection(g, next(g.objects(union, OWL.unionOf))))
        assert members == {mas.ExecutionElement, mas.CognitionProtocolExecutionReport}

    def test_protocol_lists_are_marked_multi_valued(self):
        from rdflib import Namespace

        g, mas = (
            self._graph(),
            Namespace("https://outshift-open.github.io/oxp-ontology/mas#"),
        )
        for prop in (
            "protocolsEnabled",
            "protocolsActivated",
            "agentsEnabled",
            "agentsActivated",
            "skillsEnabled",
            "skillsActivated",
        ):
            assert next(g.objects(mas[prop], mas.multiValued)).toPython() is True


class TestPackageIntegration:
    """Test package installation and imports"""

    def test_import_package(self):
        """Package can be imported"""
        import oxp_ontology

        assert oxp_ontology is not None

    def test_exposed_functions(self):
        """Package exposes public API"""
        from oxp_ontology import get_ontology_path, load_graph

        assert callable(get_ontology_path)
        assert callable(load_graph)

    def test_ontology_files_bundled(self):
        """All TTL files are bundled in package"""
        import oxp_ontology

        package_dir = Path(oxp_ontology.__file__).parent

        for filename in ONTOLOGY_FILES.values():
            ttl_path = package_dir / filename
            assert ttl_path.exists(), f"Missing bundled file: {filename}"
