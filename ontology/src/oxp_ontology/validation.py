# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rdflib import OWL, RDF, RDFS, BNode, Graph, URIRef
from rdflib.namespace import SH

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-rc(\d+))?$")

_SRC = Path(__file__).resolve().parent
ONTOLOGY_FILES = [
    _SRC / "mas-ontology.ttl",
    _SRC / "semantic-ontology.ttl",
    _SRC / "metrics-ontology.ttl",
    _SRC / "analysis-ontology.ttl",
    _SRC / "insight-ontology.ttl",
]
PRIOR_VERSION_OPTIONAL = {
    _SRC / "analysis-ontology.ttl",
    _SRC / "insight-ontology.ttl",
}
SHAPES_FILE = _SRC / "mas-shapes.ttl"
CUSTOM_SHAPES_FILE = _SRC / "mas-shapes-custom.ttl"
MAS_NS = "https://outshift-open.github.io/oxp-ontology/mas#"
STALE_MAS_URIS = {
    f"{MAS_NS}embedsAs",
    f"{MAS_NS}clustersInto",
    f"{MAS_NS}connectsCluster",
    f"{MAS_NS}sequenceNumber",
    f"{MAS_NS}allSpanIds",
    f"{MAS_NS}mainSpanId",
}


@dataclass(slots=True)
class ValidationIssue:
    scope: str
    message: str


@dataclass(slots=True)
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)
    total_triples: int = 0

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclass(slots=True)
class SessionConformanceReport:
    session_id: str | None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def parse_version(value: str) -> tuple[int, int, int, int, int] | None:
    match = VERSION_RE.match(value)
    if not match:
        return None
    major, minor, patch, rc = match.groups()
    if rc is None:
        return (int(major), int(minor), int(patch), 1, 0)
    return (int(major), int(minor), int(patch), 0, int(rc))


def format_report(report: ValidationReport) -> str:
    lines = []
    for issue in report.issues:
        lines.append(f"{issue.scope}: {issue.message}")
    if report.ok:
        lines.append(f"OK ({report.total_triples} total triples across all files)")
    return "\n".join(lines)


def check_ontology_file(path: Path, *, require_prior_version: bool = True) -> list[str]:
    errors: list[str] = []
    graph = Graph()
    try:
        graph.parse(str(path), format="turtle")
    except Exception as exc:  # noqa: BLE001
        return [f"Parse error: {exc}"]

    ontologies = list(graph.subjects(RDF.type, OWL.Ontology))
    if not ontologies:
        errors.append("No owl:Ontology declaration")
    elif len(ontologies) > 1:
        errors.append(f"Multiple owl:Ontology declarations ({len(ontologies)})")

    versions = [str(value) for value in graph.objects(None, OWL.versionInfo)]
    if not versions:
        errors.append("Missing owl:versionInfo")
    else:
        for version in versions:
            if parse_version(version) is None:
                errors.append(f"owl:versionInfo {version!r} is not X.Y.Z or X.Y.Z-rcN")

    prior_versions = [str(value) for value in graph.objects(None, OWL.priorVersion)]
    if require_prior_version and not prior_versions:
        errors.append("Missing owl:priorVersion")
    else:
        for uri in prior_versions:
            tail = uri.rstrip("/").split("/")[-1]
            if parse_version(tail) is None:
                errors.append(
                    f"owl:priorVersion URI {uri!r} — tail segment {tail!r} is not a valid version"
                )
            if versions and tail == versions[0]:
                errors.append(
                    f"owl:priorVersion {tail!r} equals current owl:versionInfo — must differ"
                )

    if not list(graph.subjects(RDF.type, OWL.Class)):
        errors.append("No owl:Class defined")
    if not list(graph.subjects(RDF.type, OWL.ObjectProperty)):
        errors.append("No owl:ObjectProperty defined")
    return errors


def check_shapes_file(path: Path) -> list[str]:
    errors: list[str] = []
    graph = Graph()
    try:
        graph.parse(str(path), format="turtle")
    except Exception as exc:  # noqa: BLE001
        return [f"Parse error: {exc}"]

    if not list(graph.subjects(RDF.type, SH.NodeShape)) and not list(
        graph.subjects(RDF.type, SH.PropertyShape)
    ):
        errors.append("No sh:NodeShape or sh:PropertyShape found")
    return errors


def check_stale_mas_uris() -> list[str]:
    errors: list[str] = []
    path = _SRC / "mas-ontology.ttl"
    graph = Graph()
    try:
        graph.parse(str(path), format="turtle")
    except Exception as exc:  # noqa: BLE001
        return [f"Parse error: {exc}"]

    for uri_str in STALE_MAS_URIS:
        uri = URIRef(uri_str)
        if (uri, None, None) in graph:
            errors.append(
                f"mas-ontology.ttl: stale URI <{uri_str}> still appears as triple subject"
            )
        if any(True for _ in graph.triples((None, uri, None))):
            errors.append(
                f"mas-ontology.ttl: stale URI <{uri_str}> still used as triple predicate"
            )
    return errors


def check_import_coherence(paths: list[Path] | None = None) -> list[str]:
    errors: list[str] = []
    for path in paths or ONTOLOGY_FILES:
        graph = Graph()
        try:
            graph.parse(str(path), format="turtle")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: Parse error: {exc}")
            continue

        versions = [str(value) for value in graph.objects(None, OWL.versionInfo)]
        prior_versions = [str(value) for value in graph.objects(None, OWL.priorVersion)]
        if not versions or not prior_versions:
            continue

        current = parse_version(versions[0])
        if current is None:
            continue

        for uri in prior_versions:
            tail = uri.rstrip("/").split("/")[-1]
            prior = parse_version(tail)
            if prior is None:
                continue
            if prior >= current:
                errors.append(
                    f"{path.name}: owl:priorVersion {tail!r} >= current {versions[0]!r}"
                    " (priorVersion must be an older release)"
                )
    return errors


def check_schema_naming_conventions(paths: list[Path] | None = None) -> list[str]:
    """Validate class/property naming conventions across ontology files.

    - Classes should start with upper-case (PascalCase)
    - Object/Datatype properties should start with lower-case (camelCase)
    - Local names should be unique case-insensitively (avoid case-collisions)
    """
    errors: list[str] = []
    by_lower: dict[str, set[str]] = {}

    for path in paths or ONTOLOGY_FILES:
        graph = Graph()
        try:
            graph.parse(str(path), format="turtle")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: Parse error: {exc}")
            continue

        for cls in graph.subjects(RDF.type, OWL.Class):
            if isinstance(cls, BNode):
                continue
            local = str(cls).split("#")[-1].split("/")[-1]
            if not local:
                continue
            by_lower.setdefault(local.lower(), set()).add(local)
            if not local[0].isupper():
                errors.append(
                    f"{path.name}: class {local!r} should start with an upper-case letter"
                )

        for prop_type in (OWL.ObjectProperty, OWL.DatatypeProperty):
            for prop in graph.subjects(RDF.type, prop_type):
                if isinstance(prop, BNode):
                    continue
                local = str(prop).split("#")[-1].split("/")[-1]
                if not local:
                    continue
                by_lower.setdefault(local.lower(), set()).add(local)
                if not local[0].islower():
                    errors.append(
                        f"{path.name}: property {local!r} should start with a lower-case letter"
                    )

    for forms in by_lower.values():
        if len(forms) > 1:
            errors.append(
                f"case-collision across ontology local names: {sorted(forms)}"
            )

    return errors


def check_object_property_directionality(paths: list[Path] | None = None) -> list[str]:
    """Detect duplicate bidirectional properties without explicit inverse declaration."""
    errors: list[str] = []
    directional: list[tuple[str, str, str, str, bool]] = []

    for path in paths or ONTOLOGY_FILES:
        graph = Graph()
        try:
            graph.parse(str(path), format="turtle")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{path.name}: Parse error: {exc}")
            continue

        for prop in graph.subjects(RDF.type, OWL.ObjectProperty):
            domains = list(graph.objects(prop, RDFS.domain))
            ranges = list(graph.objects(prop, RDFS.range))
            if not domains or not ranges:
                continue
            has_inverse = any(True for _ in graph.objects(prop, OWL.inverseOf))
            pname = str(prop).split("#")[-1].split("/")[-1]
            for d in domains:
                for r in ranges:
                    directional.append((pname, str(d), str(r), path.name, has_inverse))

    for i, (p1, d1, r1, f1, inv1) in enumerate(directional):
        for p2, d2, r2, f2, inv2 in directional[i + 1 :]:
            if p1 == p2:
                continue
            # Ignore self-loop class pairs (A->A) which are not directional inverses.
            if d1 == r1 and d2 == r2:
                continue
            if d1 == r2 and r1 == d2 and not inv1 and not inv2:
                errors.append(
                    f"{f1}/{f2}: bidirectional duplicate properties {p1!r} and {p2!r} "
                    "without owl:inverseOf declaration"
                )

    return errors


def check_transition_execution_contract(paths: list[Path] | None = None) -> list[str]:
    """Ensure canonical Transition->Execution mapping is declared consistently."""
    errors: list[str] = []
    target_path = _SRC / "mas-ontology.ttl"
    if paths and target_path not in paths:
        return errors

    graph = Graph()
    try:
        graph.parse(str(target_path), format="turtle")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{target_path.name}: Parse error: {exc}")
        return errors

    mas = "https://outshift-open.github.io/oxp-ontology/mas#"
    represents = URIRef(f"{mas}representsExecution")
    transition = URIRef(f"{mas}Transition")
    execution = URIRef(f"{mas}ExecutionElement")

    if (represents, RDF.type, OWL.ObjectProperty) not in graph:
        errors.append(
            "mas-ontology.ttl: representsExecution must be declared as owl:ObjectProperty"
        )
        return errors
    if (represents, RDFS.domain, transition) not in graph:
        errors.append(
            "mas-ontology.ttl: representsExecution must have domain mas:Transition"
        )
    if (represents, RDFS.range, execution) not in graph:
        errors.append(
            "mas-ontology.ttl: representsExecution must have range mas:ExecutionElement"
        )

    return errors


def validate_bundled_ontologies() -> ValidationReport:
    report = ValidationReport()

    for path in ONTOLOGY_FILES:
        graph = Graph()
        try:
            graph.parse(str(path), format="turtle")
            report.total_triples += len(graph)
        except Exception as exc:  # noqa: BLE001
            report.issues.append(ValidationIssue(path.name, f"Parse error: {exc}"))
            continue

        for error in check_ontology_file(
            path, require_prior_version=path not in PRIOR_VERSION_OPTIONAL
        ):
            report.issues.append(ValidationIssue(path.name, error))

    for shapes_file in (SHAPES_FILE, CUSTOM_SHAPES_FILE):
        shapes_graph = Graph()
        try:
            shapes_graph.parse(str(shapes_file), format="turtle")
            report.total_triples += len(shapes_graph)
        except Exception as exc:  # noqa: BLE001
            report.issues.append(
                ValidationIssue(shapes_file.name, f"Parse error: {exc}")
            )
        else:
            for error in check_shapes_file(shapes_file):
                report.issues.append(ValidationIssue(shapes_file.name, error))

    for error in check_stale_mas_uris():
        report.issues.append(ValidationIssue("stale-mas-uris", error))
    for error in check_import_coherence():
        report.issues.append(ValidationIssue("coherence", error))
    for error in check_schema_naming_conventions():
        report.issues.append(ValidationIssue("schema-naming", error))
    for error in check_object_property_directionality():
        report.issues.append(ValidationIssue("schema-directionality", error))
    for error in check_transition_execution_contract():
        report.issues.append(ValidationIssue("transition-execution-contract", error))

    return report


def validate_session_payload(payload: dict[str, Any]) -> SessionConformanceReport:
    session_id = payload.get("session_id") or payload.get("sessionId")
    report = SessionConformanceReport(session_id=session_id)

    if not isinstance(session_id, str) or not session_id:
        report.issues.append("missing session_id")

    session = payload.get("session")
    if not isinstance(session, dict):
        report.issues.append("missing session object")
    else:
        candidate = session.get("sessionId") or session.get("session_id")
        if session_id and candidate and candidate != session_id:
            report.issues.append("session object id does not match payload session_id")

    for key in ("agent_spans", "llm_spans", "tool_spans", "conversation"):
        value = payload.get(key, [])
        if value is None:
            continue
        if not isinstance(value, list):
            report.issues.append(f"{key} must be a list")

    for key, identifier_keys in {
        "agent_spans": ("spanId", "agentCallId", "id"),
        "llm_spans": ("spanId", "llmCallId", "id"),
        "tool_spans": ("spanId", "toolCallId", "id"),
    }.items():
        for index, item in enumerate(payload.get(key, []) or []):
            if not isinstance(item, dict):
                report.issues.append(f"{key}[{index}] must be an object")
                continue
            if not any(item.get(identifier_key) for identifier_key in identifier_keys):
                report.issues.append(f"{key}[{index}] is missing an identifier")
            if session_id and item.get("sessionId") not in (None, session_id):
                report.issues.append(f"{key}[{index}] has mismatched sessionId")

    return report


def fetch_session_payload_via_oxp_api(
    session_id: str, *, requirements: Any | None = None
) -> dict[str, Any]:
    from oxp.interfaces.models import MetricRequirements
    from oxp.providers import Neo4jGraphProvider

    provider = Neo4jGraphProvider()
    try:
        return provider.fetch(session_id, requirements or MetricRequirements())
    finally:
        close = getattr(provider, "close", None)
        if callable(close):
            close()
