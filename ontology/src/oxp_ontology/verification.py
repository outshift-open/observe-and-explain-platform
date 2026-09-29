# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""Runtime SHACL verification for individual KG object instances.

Complements ``validation.py`` (which lints the bundled ontology TTL files
themselves) with instance-level conformance checking: given one constructed
node/edge object (an instance of a class generated under
``oxp_ontology.models.nodes``/``models.edges``), checks it against the
bundled SHACL shapes (``mas-shapes.ttl``) before a caller writes it to the
graph database.

Requires the ``verify`` extra (``pip install oxp-ontology[verify]``),
which pulls in ``pyshacl``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from typing import Any

from rdflib import OWL, RDF, RDFS, XSD, BNode, Graph, Literal, URIRef
from rdflib.namespace import SH

from .validation import CUSTOM_SHAPES_FILE, ONTOLOGY_FILES, SHAPES_FILE

# Fields carried by every KGBase/KGNode/KGEdge instance that are not
# ontology-declared properties and must never become RDF predicates.
_EXCLUDED_FIELDS = {
    "id",
    "node_type",
    "edge_type",
    "from_id",
    "to_id",
    "source_id",
    "target_id",
}

_CLASS_TYPES = (OWL.Class,)
_PROPERTY_TYPES = (OWL.DatatypeProperty, OWL.ObjectProperty, OWL.AnnotationProperty)


@dataclass(slots=True)
class ShapeViolation:
    path: str | None
    severity: str
    message: str


@dataclass(slots=True)
class KGVerificationReport:
    kg_type: str
    conforms: bool
    violations: list[ShapeViolation] = field(default_factory=list)

    @property
    def errors(self) -> list[ShapeViolation]:
        return [v for v in self.violations if v.severity == "Violation"]

    @property
    def warnings(self) -> list[ShapeViolation]:
        return [v for v in self.violations if v.severity == "Warning"]


class OntologyValidationError(Exception):
    """Raised when a KG object instance fails a mandatory (Violation-severity) SHACL constraint."""

    def __init__(self, report: KGVerificationReport):
        self.report = report
        details = (
            "; ".join(f"{v.path}: {v.message}" for v in report.errors)
            or "unknown violation"
        )
        super().__init__(f"{report.kg_type} failed ontology validation: {details}")


@lru_cache(maxsize=1)
def _shapes_graph() -> Graph:
    # mas-shapes.ttl only emits bare `sh:property <iri>` references -- the
    # actual sh:PropertyShape triples (sh:path/minCount/severity) live inline
    # on each property's own declaration in the ontology files. pyshacl
    # resolves sh:property against the shapes graph only (ont_graph is used
    # purely for entailment over the data graph), so those files must be
    # parsed into this graph too, or every bare reference fails to resolve.
    graph = Graph()
    for path in ONTOLOGY_FILES:
        graph.parse(str(path), format="turtle")
    graph.parse(str(SHAPES_FILE), format="turtle")
    graph.parse(str(CUSTOM_SHAPES_FILE), format="turtle")
    return graph


@lru_cache(maxsize=1)
def _ontology_graph() -> Graph:
    graph = Graph()
    for path in ONTOLOGY_FILES:
        graph.parse(str(path), format="turtle")
    return graph


@lru_cache(maxsize=1)
def _local_name_index() -> dict[str, str]:
    """Map an ontology local name (e.g. 'ConsistencyReport', 'consistencyMean') to its full URI."""
    graph = _ontology_graph()
    index: dict[str, str] = {}
    for rdf_type in (*_CLASS_TYPES, *_PROPERTY_TYPES):
        for subject in graph.subjects(RDF.type, rdf_type):
            uri = str(subject)
            local = uri.split("#")[-1].split("/")[-1]
            if local:
                index.setdefault(local, uri)
    return index


def _resolve(local_name: str) -> URIRef | None:
    uri = _local_name_index().get(local_name)
    return URIRef(uri) if uri else None


def _literal_for(prop_uri: URIRef, value: Any) -> Literal:
    """Build a Literal, casting to xsd:decimal when the property's declared range demands it.

    rdflib's automatic literal typing maps a Python ``float`` to ``xsd:double``,
    but several ontology properties (consistencyMean, anomalyThreshold, ...) are
    declared with range ``xsd:decimal`` — cast explicitly so sh:datatype checks match.
    """
    range_uri = next(_ontology_graph().objects(prop_uri, RDFS.range), None)
    if (
        range_uri == XSD.decimal
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ):
        return Literal(Decimal(str(value)), datatype=XSD.decimal)
    return Literal(value)


def _build_instance_graph(
    obj: Any, edges: Iterable[Any] | None = None
) -> tuple[Graph, URIRef | BNode]:
    kg_type = getattr(obj, "kg_type", obj.__class__.__name__)
    class_uri = _resolve(kg_type)
    if class_uri is None:
        raise ValueError(
            f"Unknown ontology class {kg_type!r}: no owl:Class with that local name."
        )

    kg_id = getattr(obj, "kg_id", None)
    subject: URIRef | BNode
    if isinstance(kg_id, str) and kg_id:
        subject = URIRef(f"urn:oxp-ontology:instance:{kg_id}")
    else:
        subject = BNode()

    graph = Graph()
    graph.add((subject, RDF.type, class_uri))

    # "id" is excluded from the field loop below because it's consumed to
    # build the subject URI instead -- but mas:id is also its own mandatory
    # sh:PropertyShape (sh:minCount 1) on mas:Element, so it still needs to
    # be asserted as a triple, or every instance spuriously fails on a
    # phantom missing id.
    own_id = getattr(obj, "id", None)
    if isinstance(own_id, str) and own_id:
        id_prop = _resolve("id")
        if id_prop is not None:
            graph.add((subject, id_prop, Literal(own_id)))

    values = obj.model_dump(mode="python", exclude_none=True)
    for field_name, value in values.items():
        if field_name in _EXCLUDED_FIELDS:
            continue
        if value == "" or value == {}:
            continue
        prop_uri = _resolve(field_name)
        if prop_uri is None:
            continue
        items = value if isinstance(value, list) else [value]
        for item in items:
            graph.add((subject, prop_uri, _literal_for(prop_uri, item)))

    # obj is validated alone, but a mandatory *relationship* (an object
    # property modeled as its own KGEdge class, e.g. ofSemanticGroup) can't
    # be expressed via obj's own fields -- it needs an edge asserting it.
    for edge in edges or ():
        edge_type = getattr(edge, "kg_type", edge.__class__.__name__)
        prop_uri = _resolve(edge_type)
        target_id = getattr(edge, "target_id", None)
        if prop_uri is None or not target_id:
            continue
        graph.add((subject, prop_uri, URIRef(f"urn:oxp-ontology:instance:{target_id}")))

    return graph, subject


def verify_kg_object(
    obj: Any, *, edges: Iterable[Any] | None = None
) -> KGVerificationReport:
    """Validate one KG node/edge instance against the bundled SHACL shapes.

    ``obj`` is expected to expose ``kg_type``, ``kg_id``, and ``model_dump``
    (i.e. a ``oxp_ontology.models.base.KGBase`` instance), but any object
    with that shape works.

    ``edges`` lets you assert outgoing relationships from ``obj`` that the
    ontology models as separate ``KGEdge`` classes rather than fields on
    ``obj`` itself (e.g. ``ofSemanticGroup``, ``concerns``) -- pass real edge
    instances (``source_id`` is not checked against ``obj``'s own id; only
    ``kg_type``/``target_id`` are used) so a mandatory relationship's SHACL
    shape has something to actually validate.

    Only Violation-severity SHACL results affect ``report.conforms`` —
    Warning-severity results (recommended-but-optional properties) are
    collected in ``report.violations``/``report.warnings`` but never cause
    ``conforms`` to be False.
    """
    try:
        import pyshacl
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ImportError(
            "verify_kg_object() requires pyshacl. Install with 'pip install oxp-ontology[verify]'."
        ) from exc

    kg_type = getattr(obj, "kg_type", obj.__class__.__name__)
    data_graph, subject = _build_instance_graph(obj, edges)

    validate_kwargs: dict[str, Any] = {
        "shacl_graph": _shapes_graph(),
        "ont_graph": _ontology_graph(),
        "inference": "none",
        "advanced": True,
    }
    # pyshacl's focus_nodes only accepts URIRefs/curie strings, not blank nodes.
    if isinstance(subject, URIRef):
        validate_kwargs["focus_nodes"] = [subject]

    # Deliberately NOT passing allow_warnings=True: pyshacl drops Warning-severity
    # results from the report graph entirely under that flag (not just from
    # `conforms`), which would hide recommended-but-missing properties from
    # callers. Instead, run with pyshacl's default severity handling (which
    # reports every result and treats any of them as non-conforming) and
    # recompute `conforms` ourselves below from the parsed violations, so it
    # reflects Violation-severity results only.
    _pyshacl_conforms, results_graph, _results_text = pyshacl.validate(
        data_graph, **validate_kwargs
    )

    seen: set[tuple[str | None, str]] = set()
    violations: list[ShapeViolation] = []
    for result in results_graph.subjects(RDF.type, SH.ValidationResult):
        # A failing sh:node-nested shape (used throughout mas-shapes.ttl for
        # class-hierarchy inheritance) is wrapped by pyshacl in an outer
        # NodeConstraintComponent result whose own sh:resultSeverity is
        # always sh:Violation, regardless of the real severity of whatever
        # actually failed inside it (e.g. a missing Warning-only recommended
        # property). That inner cause is already present as its own
        # independent top-level ValidationResult (reachable here on a later
        # iteration), so the wrapper -- identifiable by having sh:detail
        # children -- is skipped entirely rather than counted as a second,
        # spuriously Violation-severity result.
        if next(results_graph.objects(result, SH.detail), None) is not None:
            continue
        severity_uri = next(results_graph.objects(result, SH.resultSeverity), None)
        severity = (
            str(severity_uri).rsplit("#", maxsplit=1)[-1]
            if severity_uri
            else "Violation"
        )
        message = next(results_graph.objects(result, SH.resultMessage), None)
        path = next(results_graph.objects(result, SH.resultPath), None)
        violation = ShapeViolation(
            path=str(path).split("#")[-1] if path else None,
            severity=severity,
            message=str(message) if message else "SHACL constraint violated.",
        )
        # A concrete report class's shape and the abstract SemanticAnalysisReportShape
        # (targeted via subclass entailment) both check the same inherited
        # properties, so the same field/severity is reported twice — collapse to
        # the first (concrete-shape) message.
        key = (violation.path, violation.severity)
        if key in seen:
            continue
        seen.add(key)
        violations.append(violation)

    conforms = not any(v.severity == "Violation" for v in violations)
    return KGVerificationReport(
        kg_type=kg_type, conforms=conforms, violations=violations
    )
