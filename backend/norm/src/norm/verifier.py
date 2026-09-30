#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Structural and SHACL checks for a Knowledge Graph.

Graph-shape invariants (containment, state reachability, temporal enclosure)
live in SHACL (``mas-ontology.ttl``'s inline property shapes plus
``mas-shapes.ttl``/``mas-shapes-custom.ttl``, run via
:func:`run_shacl_validation`) rather than as hand-rolled Python, so there is
a single source of truth for what a valid KG looks like.

Structural checks in this module
---------------------------------
1. :func:`check_unknown_node_types` — every node_type must be declared in
   :data:`KNOWN_NODE_TYPES` (derived from the MAS ontology class hierarchy).
2. :func:`check_unknown_edge_types` — every edge_type must be declared in
   :data:`KNOWN_EDGE_TYPES`.
3. :func:`check_edge_domain_range` — every edge's endpoints must match its
   edge_type's declared rdfs:domain/rdfs:range (:data:`PROPERTY_DOMAIN_RANGE`,
   subclasses included) -- catches a *valid* class used with a *valid*
   property in a pattern the ontology never declared, which 1/2 above cannot:
   both terms there are real, only the combination is wrong.
4. :func:`check_orphaned_edges` — every edge's endpoints must reference a
   node present in the same batch.
5. :func:`run_shacl_validation` — runs ``mas-ontology.ttl`` +
   ``mas-shapes.ttl`` + ``mas-shapes-custom.ttl`` against the KG via pyshacl;
   raises :class:`KGCheckSkipped` if pyshacl/rdflib aren't installed, so a
   missing optional dependency is never mistaken for a pass.
"""

from __future__ import annotations

import json
import logging
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ---------------------------------------------------------------------------
# Ontology index — derives all validation constants from mas-ontology.ttl via
# the oxp_ontology package.  No intermediate JSON schema file required.
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)


class _OntologyIndex:
    """Loads all validation constants from ``mas-ontology.ttl``.

    From the ``oxp_ontology`` package (see ``norm.ontology``). Every
    constant is derived from the ontology graph. Nothing is hardcoded.

    Recognised namespace (used to filter triples to the MAS vocabulary):
    ``mas:`` ``https://outshift-open.github.io/oxp-ontology/mas#``
    """

    _NS = "https://outshift-open.github.io/oxp-ontology/mas#"

    def __init__(self) -> None:
        self.known_node_types: frozenset[str] = frozenset()
        self.known_edge_types: frozenset[str] = frozenset()
        self.known_attrs_lower: Dict[str, str] = {}
        self.parent_classes: Dict[str, List[str]] = {}
        # property local name -> (domain class local names, range class local
        # names), both as lists to support owl:unionOf domains/ranges (e.g.
        # hasInitialState/hasFinalState's domain is unionOf(Session,
        # ExecutionElement)). A property with no rdfs:domain/rdfs:range
        # declared at all gets an empty list on that side -- nothing to
        # check, not "anything goes".
        self.property_domain_range: Dict[str, Tuple[List[str], List[str]]] = {}
        self.loaded: bool = False  # True iff the ontology TTL parsed successfully
        self._load()

    def _load(self) -> None:
        try:
            import rdflib  # type: ignore

            from norm.ontology import resolve_kg_ontology_paths

            ttl_files: List[Path] = resolve_kg_ontology_paths()
        except ImportError as exc:  # pragma: no cover
            logger.warning(
                (
                    "oxp_ontology not available — _OntologyIndex empty "
                    "(validation will block ingest): %s"
                ),
                exc,
            )
            return

        OWL = rdflib.namespace.OWL
        RDFS = rdflib.namespace.RDFS
        RDF = rdflib.RDF

        if not ttl_files:
            logger.warning("_OntologyIndex: no ontology TTLs resolved — ingest will be blocked.")
            return

        # ── Load into one combined graph ───────────────────────────────────
        g = rdflib.Graph()
        loaded_count = 0
        for ttl in ttl_files:
            try:
                before = len(g)
                g.parse(str(ttl), format="turtle")
                logger.debug("Loaded TTL: %s (+%d triples)", ttl.name, len(g) - before)
                loaded_count += 1
            except Exception as exc:
                logger.warning("Could not parse %s: %s", ttl, exc)

        if loaded_count == 0:
            logger.warning("_OntologyIndex: no TTL could be loaded — ingest will be blocked.")
            return

        # ── Helpers ────────────────────────────────────────────────────────
        def _in_ns(iri: str) -> bool:
            return iri.startswith(self._NS)

        def _local(iri: str) -> str:
            return iri.split("#")[-1].split("/")[-1]

        def _local_names(rdf_type: Any) -> frozenset[str]:
            return frozenset(
                _local(str(s))
                for s, _, _ in g.triples((None, RDF.type, rdf_type))
                if _in_ns(str(s))
            )

        # ── Populate index ─────────────────────────────────────────────────
        self.known_node_types = _local_names(OWL.Class)
        self.known_edge_types = _local_names(OWL.ObjectProperty)
        dt_names = list(_local_names(OWL.DatatypeProperty))
        self.known_attrs_lower = {n.lower(): n for n in dt_names}

        # Direct rdfs:subClassOf → parent_classes map
        parent_map: Dict[str, List[str]] = {}
        for cls, _, parent in g.triples((None, RDFS.subClassOf, None)):
            if not _in_ns(str(cls)) or not _in_ns(str(parent)):
                continue
            parent_map.setdefault(_local(str(cls)), []).append(_local(str(parent)))
        self.parent_classes = parent_map

        # rdfs:domain/rdfs:range for every declared ObjectProperty -- derived
        # directly from the ontology, not hand-maintained, so a check built
        # on this automatically covers every property as its own
        # domain/range declaration evolves (see check_edge_domain_range).
        # owl:unionOf domains/ranges (e.g. hasInitialState/hasFinalState's
        # domain is unionOf(Session, ExecutionElement)) expand to every
        # member of the union.
        def _class_terms(node: Any) -> List[str]:
            union = g.value(node, OWL.unionOf)
            if union is not None:
                return [_local(str(item)) for item in g.items(union) if _in_ns(str(item))]
            return [_local(str(node))] if _in_ns(str(node)) else []

        domain_range: Dict[str, Tuple[List[str], List[str]]] = {}
        for prop in g.subjects(RDF.type, OWL.ObjectProperty):
            if not _in_ns(str(prop)):
                continue
            domains: List[str] = []
            for d in g.objects(prop, RDFS.domain):
                domains.extend(_class_terms(d))
            ranges: List[str] = []
            for r in g.objects(prop, RDFS.range):
                ranges.extend(_class_terms(r))
            domain_range[_local(str(prop))] = (domains, ranges)
        self.property_domain_range = domain_range

        logger.debug(
            "_OntologyIndex: %d node types, %d edge types, %d attrs, %d TTLs loaded",
            len(self.known_node_types),
            len(self.known_edge_types),
            len(self.known_attrs_lower),
            loaded_count,
        )
        self.loaded = len(self.known_node_types) > 0 and loaded_count == len(ttl_files)


_ONT = _OntologyIndex()

# ---------------------------------------------------------------------------
# Invariant checkers
# ---------------------------------------------------------------------------

CheckResult = Tuple[bool, List[Any]]  # (passed, list_of_violation_dicts)


@dataclass
class _ValidationMessage:
    severity: str
    message: str


# Node/edge type sets derived from the combined ontology graph via _ONT.
KNOWN_NODE_TYPES: frozenset[str] = _ONT.known_node_types
KNOWN_EDGE_TYPES: frozenset[str] = _ONT.known_edge_types

# class -> [direct rdfs:subClassOf parents]. Exposed so check_edge_domain_range's
# _class_or_ancestor_in() can walk a node's ancestry when checking whether an
# edge's endpoint type satisfies a declared rdfs:domain/rdfs:range.
PARENT_CLASSES: Dict[str, List[str]] = _ONT.parent_classes

# property local name -> (domain class local names, range class local
# names), derived directly from every declared ObjectProperty's
# rdfs:domain/rdfs:range -- see check_edge_domain_range, which is built on
# this so it automatically covers every property as the ontology's own
# domain/range declarations evolve, with no hand-authored shape needed.
PROPERTY_DOMAIN_RANGE: Dict[str, Tuple[List[str], List[str]]] = _ONT.property_domain_range


def check_unknown_node_types(nodes: List[Dict], edges: List[Dict]) -> CheckResult:
    """Every node must have a node_type that is declared in the MAS ontology.

    Unknown types indicate a normalisation bug or schema drift — surfaced as
    violations so they are caught before Neo4j ingestion.
    """
    violations: List[Any] = []
    seen_unknown: set[str] = set()
    for n in nodes:
        ntype = n.get("node_type", "")
        if not ntype:
            nid = n.get("id") or "?"
            violations.append(
                {
                    "sub": "node",
                    "status": "missing",
                    "attr": "node_type",
                    "node_id": nid,
                }
            )
        elif ntype not in KNOWN_NODE_TYPES and ntype not in seen_unknown:
            seen_unknown.add(ntype)
            violations.append(
                {
                    "sub": "node",
                    "status": "spurious",
                    "attr": "node_type",
                    "cur": ntype,
                }
            )
    return len(violations) == 0, violations


def check_unknown_edge_types(nodes: List[Dict], edges: List[Dict]) -> CheckResult:
    """Every edge must have an edge_type that is declared in the MAS ontology.

    Unknown edge types indicate a normalisation bug or schema drift.
    """
    violations: List[Any] = []
    seen_unknown: set[str] = set()
    for e in edges:
        etype = e.get("edge_type", "")
        if not etype:
            violations.append(
                {
                    "sub": "edge",
                    "status": "missing",
                    "attr": "edge_type",
                    "from_id": e.get("from_id", "?"),
                    "to_id": e.get("to_id", "?"),
                }
            )
        elif etype not in KNOWN_EDGE_TYPES and etype not in seen_unknown:
            seen_unknown.add(etype)
            violations.append(
                {
                    "sub": "edge",
                    "status": "spurious",
                    "attr": "edge_type",
                    "cur": etype,
                }
            )
    return len(violations) == 0, violations


def _class_or_ancestor_in(node_type: str, allowed: List[str]) -> bool:
    """True if node_type itself, or any of its rdfs:subClassOf* ancestors
    (via PARENT_CLASSES), is in allowed."""
    if not allowed:
        return True  # nothing declared on this side -- nothing to check
    if node_type in allowed:
        return True
    seen: set[str] = set()
    stack = [node_type]
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        for parent in PARENT_CLASSES.get(cls, []):
            if parent in allowed:
                return True
            stack.append(parent)
    return False


def check_edge_domain_range(nodes: List[Dict], edges: List[Dict]) -> CheckResult:
    """Every edge's endpoints must match its edge_type's declared
    rdfs:domain/rdfs:range in the ontology (subclasses of the declared
    class count too).

    Unlike ``check_unknown_edge_types`` (which only checks that the
    edge_type *name* is a real, declared property), this checks that the
    property is used with the *right kind of node* on each end -- a node
    using genuinely-declared ontology terms (a valid class, a valid
    property) still passes that check even when the specific pattern of
    use is wrong (e.g. a Session connected to a Run node via the real
    ``maskg:contains`` property: both terms are real, the pattern was
    never valid). This check is derived directly from
    :data:`PROPERTY_DOMAIN_RANGE` (every declared ObjectProperty's own
    rdfs:domain/rdfs:range), so it automatically covers every property as
    the ontology's own declarations evolve -- no per-property shape to
    remember to add.

    A property with no rdfs:domain/rdfs:range declared at all is not
    checked on that side (nothing to check, not "anything goes" --
    contrast with a declared-but-not-satisfied domain/range, which *is* a
    violation).
    """
    if not PROPERTY_DOMAIN_RANGE:
        return True, []  # ontology unavailable; check_unknown_* already reports that
    node_by_id: Dict[str, Dict[str, Any]] = {str(n["id"]): n for n in nodes if n.get("id")}

    violations: List[Any] = []
    for e in edges:
        etype = str(e.get("edge_type", ""))
        dr = PROPERTY_DOMAIN_RANGE.get(etype)
        if dr is None:
            continue  # unknown edge_type entirely -- check_unknown_edge_types' job
        domains, ranges = dr
        src = node_by_id.get(str(e.get("from_id") or ""))
        if src is not None and not _class_or_ancestor_in(str(src.get("node_type", "")), domains):
            violations.append(
                {
                    "sub": "edge",
                    "status": "domain_mismatch",
                    "edge_type": etype,
                    "from_id": e.get("from_id"),
                    "node_type": src.get("node_type"),
                    "expected": domains,
                }
            )
        dst = node_by_id.get(str(e.get("to_id") or ""))
        if dst is not None and not _class_or_ancestor_in(str(dst.get("node_type", "")), ranges):
            violations.append(
                {
                    "sub": "edge",
                    "status": "range_mismatch",
                    "edge_type": etype,
                    "to_id": e.get("to_id"),
                    "node_type": dst.get("node_type"),
                    "expected": ranges,
                }
            )
    return len(violations) == 0, violations


def check_orphaned_edges(nodes: List[Dict], edges: List[Dict]) -> CheckResult:
    """Check for edges whose endpoints are not present in the node list.

    This is a critical structural invariant: in a normal KG push, every edge
    must reference nodes that exist in the same batch. Orphaned edges indicate
    one of two upstream bugs:

    1. **Node creation failure**: A node should exist but was filtered out
       (e.g., missing 'id' field, validation failure, denormalization bug).

    2. **Edge creation bug**: An edge was created with invalid from_id/to_id
       that doesn't match any real node.

    Annotation cross-references are legitimate (e.g., Metric nodes referencing
    existing Session nodes not in the current batch) but should be pushed via
    a separate annotation push path that documents that behavior. This check
    helps catch unintentional orphaned edges in normal KG building.

    NOTE: This check does NOT run for annotation pushes where dangling
    references are expected.
    """
    node_ids = {str(n.get("id", "")) for n in nodes if n.get("id")}
    violations: List[Any] = []

    for e in edges:
        from_id = str(e.get("from_id") or e.get("source") or "")
        to_id = str(e.get("to_id") or e.get("target") or "")
        edge_type = e.get("edge_type", "?")

        if from_id and from_id not in node_ids:
            violations.append(
                {
                    "sub": "edge",
                    "status": "orphaned_from",
                    "edge_type": edge_type,
                    "from_id": from_id,
                    "to_id": to_id,
                    "msg": f"from_id '{from_id}' not in node list",
                }
            )

        if to_id and to_id not in node_ids:
            violations.append(
                {
                    "sub": "edge",
                    "status": "orphaned_to",
                    "edge_type": edge_type,
                    "from_id": from_id,
                    "to_id": to_id,
                    "msg": f"to_id '{to_id}' not in node list",
                }
            )

    return len(violations) == 0, violations


# ---------------------------------------------------------------------------
# Optional SHACL validation
# ---------------------------------------------------------------------------


class KGCheckSkipped(Exception):
    """Raised when a check cannot run at all in this environment.

    This is distinct from both "pass" (ran, found nothing) and "error" (ran,
    found a problem, or crashed unexpectedly): the check never executed, so
    it must never be reported the same way a real pass would be -- a caller
    that only checks ``error_count``/``passed`` must not be able to mistake
    "skipped" for "clean validation run".
    """


def run_shacl_validation(
    nodes: List[Dict],
    edges: List[Dict],
    ontology_path: Path,
    run_id: str,
    *,
    strict: bool = False,
) -> Tuple[bool, List[Any], List[Any]]:
    """Run pyshacl against a JSON-LD representation of the KG.

    Uses ``mas-ontology.ttl`` + ``mas-shapes.ttl`` + ``mas-shapes-custom.ttl``
    as the SHACL shapes graph — ``mas-shapes.ttl`` only emits bare
    ``sh:property`` references to inline ``sh:PropertyShape``s declared on
    properties in ``mas-ontology.ttl`` itself, so the ontology file must be
    in the same graph or those references never resolve (same reasoning as
    ``oxp_ontology.verification._shapes_graph()``).

    Returns ``(passed, violations, warnings)`` where SHACL warnings remain
    warnings unless ``strict=True``.

    Raises:
        KGCheckSkipped: if pyshacl or rdflib are not installed. The caller
            must surface this as a distinct "skipped" outcome, not a pass.
    """
    try:
        import pyshacl  # type: ignore
        import rdflib
    except ImportError as exc:
        raise KGCheckSkipped(
            "shacl check requires pyshacl and rdflib (pip install 'norm[graph]')"
        ) from exc

    from norm.ontology import (
        resolve_all_ontology_paths,
        resolve_mas_shapes_custom_path,
        resolve_mas_shapes_path,
    )

    try:
        shapes_files = [
            path
            for path in (
                *resolve_all_ontology_paths(),
                resolve_mas_shapes_path(),
                resolve_mas_shapes_custom_path(),
            )
            if path is not None and path.exists()
        ]
    except ImportError as exc:
        raise KGCheckSkipped(
            "shacl check requires oxp_ontology to resolve mas-shapes.ttl "
            "(pip install 'norm[graph]')"
        ) from exc
    if not shapes_files:
        raise KGCheckSkipped(
            "shacl check requires oxp_ontology to resolve mas-ontology.ttl/"
            "mas-shapes.ttl/mas-shapes-custom.ttl"
        )

    doc = nodes_edges_to_jsonld(nodes, edges, run_id)

    data_graph = rdflib.Graph()
    # rdflib JSON-LD parser currently emits a ConjunctiveGraph deprecation warning
    # internally; suppress that third-party warning at this call site.
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"ConjunctiveGraph is deprecated, use Dataset instead.*",
            category=DeprecationWarning,
        )
        data_graph.parse(data=json.dumps(doc), format="json-ld")

    shacl_graph = rdflib.Graph()
    for shapes_file in shapes_files:
        shacl_graph.parse(str(shapes_file), format="turtle")

    SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")

    conforms, report_graph, report_text = pyshacl.validate(
        data_graph,
        shacl_graph=shacl_graph,
        inference="rdfs",
        abort_on_first=False,
    )
    violations: List[Any] = []
    warning_items: List[Any] = []

    for result in report_graph.subjects(rdflib.RDF.type, SH.ValidationResult):
        # A failing sh:node-nested shape (used throughout mas-shapes.ttl for
        # class-hierarchy inheritance, e.g. ToolShape -> CapabilityShape ->
        # StructuralElementShape -> ElementShape) is wrapped by pyshacl in an
        # outer NodeConstraintComponent result whose own sh:resultSeverity is
        # always sh:Violation, regardless of the real severity of whatever
        # actually failed inside it (e.g. a missing Warning-only recommended
        # property like description). That inner cause is already present as
        # its own independent top-level ValidationResult (reachable here on a
        # later iteration), so the wrapper -- identifiable by having
        # sh:detail children -- is skipped entirely rather than counted as a
        # second, spuriously Violation-severity result.
        if next(report_graph.objects(result, SH.detail), None) is not None:
            continue
        severity_node = report_graph.value(result, SH.resultSeverity)
        focus_node = report_graph.value(result, SH.focusNode)
        result_path = report_graph.value(result, SH.resultPath)
        result_message = report_graph.value(result, SH.resultMessage)
        source_shape = report_graph.value(result, SH.sourceShape)

        severity_text = (
            str(severity_node).rsplit("#", 1)[-1].lower() if severity_node else "violation"
        )
        status = "warning" if severity_text == "warning" and not strict else "error"

        detail_parts = []
        if result_message:
            detail_parts.append(str(result_message))
        if focus_node:
            detail_parts.append(f"focus={focus_node}")
        if result_path:
            detail_parts.append(f"path={result_path}")
        if source_shape:
            detail_parts.append(f"shape={source_shape}")
        detail = " | ".join(detail_parts) or (
            report_text[:4000] if report_text else "SHACL validation failed"
        )

        item = _ValidationMessage(status, detail)
        if status == "warning":
            warning_items.append(item)
        else:
            violations.append(item)

    passed = not violations
    return passed, violations, warning_items


def nodes_edges_to_jsonld(
    nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]], run_id: str
) -> Dict[str, Any]:
    """Build a JSON-LD document (``@context`` + ``@graph``) from KG nodes/edges.

    Extracted from :func:`run_shacl_validation` so callers can obtain the
    intermediate JSON-LD representation (e.g. to persist or inspect) without
    also running pyshacl. Uses the same MAS IRI mapping SHACL validates
    against, so a JSON-LD doc built here is exactly what
    ``run_shacl_validation`` feeds to pyshacl.

    Every node uses the ontology's single generic ``id`` as its identity —
    there is no more per-type identity field (``callId``/``stateNodeId``/
    ``transitionId``/etc.) to branch on.
    """
    MAS = "https://outshift-open.github.io/oxp-ontology/mas#"

    # Maps camelCase node dict keys → MAS camelCase property IRIs. Kept to
    # the ontology's actual current field set (see oxp_ontology.models.nodes).
    _PROP_MAP = [
        ("name", "name"),
        ("sessionId", "sessionId"),
        ("startTime", "startTime"),
        ("endTime", "endTime"),
        ("duration", "duration"),
        ("declared", "declared"),
        ("description", "description"),
        ("provider", "provider"),
        ("content", "content"),
        ("spanId", "spanId"),
        ("parentSpanId", "parentSpanId"),
        ("totalTokenCount", "totalTokenCount"),
        ("promptTokenCount", "promptTokenCount"),
        ("completionTokenCount", "completionTokenCount"),
        ("temperature", "temperature"),
        ("finishReason", "finishReason"),
        ("responseId", "responseId"),
        ("cacheReadTokenCount", "cacheReadTokenCount"),
    ]
    _DECIMAL_PROPS = {"startTime", "endTime", "duration", "temperature"}
    _INTEGER_PROPS = {
        "promptTokenCount",
        "completionTokenCount",
        "totalTokenCount",
        "cacheReadTokenCount",
    }
    _BOOLEAN_PROPS = {"declared"}

    ld_nodes = []
    node_iri_by_local_id: Dict[str, str] = {}
    entry_by_local_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        ntype = n.get("node_type")
        local_id = n.get("id")
        if not ntype or not local_id:
            continue
        local_id = str(local_id)

        entry: Dict[str, Any] = {
            "@id": f"urn:mas:{ntype.lower()}:{local_id}",
            "@type": f"{MAS}{ntype}",
            # mas:id is Element's own mandatory (sh:minCount 1) PropertyShape,
            # not just the URN-building input -- it must be asserted as a
            # triple too, or every instance spuriously fails on a phantom
            # missing id (see oxp_ontology.verification._build_instance_graph).
            f"{MAS}id": {"@value": local_id, "@type": "xsd:string"},
        }
        node_iri_by_local_id[local_id] = entry["@id"]
        entry_by_local_id[local_id] = entry

        for key, prop in _PROP_MAP:
            val = n.get(key)
            # An empty string is norm's "field legitimately has nothing
            # to say" placeholder -- treating it as absent (no triple at all)
            # rather than as `str(val)` is required for every Warning-severity
            # sh:minCount check in mas-shapes.ttl on these fields to mean
            # anything.
            if val is None or val == "":
                continue
            iri = f"{MAS}{prop}"
            if prop in _DECIMAL_PROPS:
                try:
                    entry[iri] = {"@value": str(float(val)), "@type": "xsd:decimal"}
                except (TypeError, ValueError):
                    pass
            elif prop in _INTEGER_PROPS:
                try:
                    entry[iri] = {"@value": str(int(val)), "@type": "xsd:integer"}
                except (TypeError, ValueError):
                    pass
            elif prop in _BOOLEAN_PROPS:
                entry[iri] = {
                    "@value": "true" if val else "false",
                    "@type": "xsd:boolean",
                }
            else:
                entry[iri] = {"@value": str(val), "@type": "xsd:string"}

        ld_nodes.append(entry)

    # Materialise ontology object properties from graph edges so SHACL sees
    # containment, execution, and trajectory links in the RDF view built for
    # validation.
    edge_to_obj_prop = {
        "hasMASCall": f"{MAS}hasMASCall",
        "hasAgentCall": f"{MAS}hasAgentCall",
        "hasToolCall": f"{MAS}hasToolCall",
        "hasLLMCall": f"{MAS}hasLLMCall",
        "hasProcessingCall": f"{MAS}hasProcessingCall",
        "hasState": f"{MAS}hasState",
        "hasInitialState": f"{MAS}hasInitialState",
        "hasFinalState": f"{MAS}hasFinalState",
        "executesAgent": f"{MAS}executesAgent",
        "executesLLM": f"{MAS}executesLLM",
        "executesTool": f"{MAS}executesTool",
        "executesProcessing": f"{MAS}executesProcessing",
        "executesMAS": f"{MAS}executesMAS",
        "executesSession": f"{MAS}executesSession",
        "executes": f"{MAS}executes",
        "belongsToMAS": f"{MAS}belongsToMAS",
        "belongsToMASCall": f"{MAS}belongsToMASCall",
        "usesCapability": f"{MAS}usesCapability",
        "usesLLM": f"{MAS}usesLLM",
        "usesTool": f"{MAS}usesTool",
        "usesProcessing": f"{MAS}usesProcessing",
        "inputTo": f"{MAS}inputTo",
        "leadsTo": f"{MAS}leadsTo",
        "correspondsToTransition": f"{MAS}correspondsToTransition",
        "representsExecution": f"{MAS}representsExecution",
        "represents": f"{MAS}represents",
        "containsSession": f"{MAS}containsSession",
        "hasMedioidSession": f"{MAS}hasMedioidSession",
    }
    for e in edges:
        prop_iri = edge_to_obj_prop.get(str(e.get("edge_type", "")))
        if not prop_iri:
            continue
        src_local = str(e.get("from_id") or "")
        dst_local = str(e.get("to_id") or "")
        src_entry = entry_by_local_id.get(src_local)
        dst_iri = node_iri_by_local_id.get(dst_local)
        if not src_entry or not dst_iri:
            continue

        existing = src_entry.get(prop_iri)
        obj_ref = {"@id": dst_iri}
        if existing is None:
            src_entry[prop_iri] = obj_ref
        elif isinstance(existing, list):
            if obj_ref not in existing:
                existing.append(obj_ref)
        elif existing != obj_ref:
            src_entry[prop_iri] = [existing, obj_ref]

    doc = {
        "@context": {
            "mas": MAS,
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "owl": "http://www.w3.org/2002/07/owl#",
        },
        "@graph": ld_nodes,
    }
    return doc


def write_jsonld(doc: Dict[str, Any], path: str | Path) -> Path:
    """Write a JSON-LD document (as built by :func:`nodes_edges_to_jsonld`) to disk.

    Mirrors :func:`norm.compare.write_kg_json`'s shape/behavior for the
    JSON-LD intermediate representation.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return out


def read_jsonld(path: str | Path) -> Dict[str, Any]:
    """Read a JSON-LD document written by :func:`write_jsonld`."""
    with Path(path).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise TypeError("JSON-LD document must deserialize to a dict")
    return data


# ---------------------------------------------------------------------------
# Pipeline step
# ---------------------------------------------------------------------------


_STRUCTURAL_CHECKS = (
    check_unknown_node_types,
    check_unknown_edge_types,
    check_edge_domain_range,
    check_orphaned_edges,
)


def verify_kg(
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
    run_id: str = "",
    *,
    ontology_path: Path | str | None = None,
    strict: bool = False,
) -> Dict[str, Any]:
    """Run every structural check plus SHACL and return one combined report."""
    resolved_path: Path | None
    try:
        from norm.ontology import resolve_mas_ontology_path

        resolved_path = Path(ontology_path) if ontology_path else resolve_mas_ontology_path(None)
    except ImportError as exc:
        return {
            "ok": True,
            "structural_checks": {"skipped": {"ok": True, "violations": [], "reason": str(exc)}},
            "shacl": {"skipped": True, "reason": str(exc)},
        }

    structural_checks: Dict[str, Any] = {}
    for check in _STRUCTURAL_CHECKS:
        ok, violations = check(nodes, edges)
        structural_checks[check.__name__] = {"ok": ok, "violations": violations}

    try:
        shacl_ok, shacl_violations, shacl_warnings = run_shacl_validation(
            nodes, edges, resolved_path, run_id, strict=strict
        )
        shacl_report: Dict[str, Any] = {
            "skipped": False,
            "ok": shacl_ok,
            "violations": shacl_violations,
            "warnings": shacl_warnings,
        }
    except KGCheckSkipped as exc:
        shacl_report = {"skipped": True, "reason": str(exc)}

    ok = all(c["ok"] for c in structural_checks.values()) and shacl_report.get("ok", True)
    return {"ok": ok, "structural_checks": structural_checks, "shacl": shacl_report}
