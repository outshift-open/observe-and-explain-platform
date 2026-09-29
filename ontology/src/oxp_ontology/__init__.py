# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

import warnings
from pathlib import Path

from .validation import (
    SessionConformanceReport,
    ValidationIssue,
    ValidationReport,
    fetch_session_payload_via_oxp_api,
    format_report,
    parse_version,
    validate_bundled_ontologies,
    validate_session_payload,
)
from .verification import (
    KGVerificationReport,
    OntologyValidationError,
    ShapeViolation,
    verify_kg_object,
)

# Expose package version
__version__ = "1.1.1"

__all__ = [
    "KGVerificationReport",
    "OntologyService",
    "OntologyValidationError",
    "SessionConformanceReport",
    "ShapeViolation",
    "ValidationIssue",
    "ValidationReport",
    "__version__",
    "fetch_session_payload_via_oxp_api",
    "format_report",
    "get_ontology_path",
    "load_graph",
    "parse_version",
    "validate_bundled_ontologies",
    "validate_session_payload",
    "verify_kg_object",
]


ONTOLOGY_FILES = {
    "mas": "mas-ontology.ttl",
    "mas-shapes": "mas-shapes.ttl",
    "mas-shapes-custom": "mas-shapes-custom.ttl",
    "semantic": "semantic-ontology.ttl",
    "metrics": "metrics-ontology.ttl",
    "analysis": "analysis-ontology.ttl",
    "insight": "insight-ontology.ttl",
}


def get_ontology_path(name: str = "mas") -> Path:
    """
    Returns the absolute path to a bundled ontology .ttl file.

    Args:
        name: One of 'mas', 'semantic', 'metrics', 'analysis', 'insight'
              (or exact filename with .ttl extension)
    """
    # Normalize name (remove extension if present)
    base_name = name.removesuffix(".ttl")

    # Map friendly names to filenames or fallback to input
    filename = ONTOLOGY_FILES.get(base_name, f"{base_name}.ttl")

    base_dir = Path(__file__).parent
    file_path = base_dir / filename

    if not file_path.exists():
        # Try direct lookup in case unmapped name was passed
        file_path = base_dir / f"{base_name}.ttl"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Ontology file '{filename}' not found in {base_dir}"
            )

    return file_path


def load_graph(name: str = "mas-ontology"):
    """
    Helper to load the ontology into an rdflib Graph.
    Requires rdflib to be installed.
    """
    try:
        import rdflib
    except ImportError:
        raise ImportError(
            "rdflib is required to use load_graph(). Install it with 'pip install rdflib'"
        )

    g = rdflib.Graph()
    path = get_ontology_path(name)
    g.parse(str(path), format="turtle")
    return g


class OntologyService:
    """
    Central service for querying ontology hierarchy and relationships.
    Provided by the ontology package to ensure consistency across consumers.
    """

    _instance = None

    def __init__(self):
        import importlib.util

        if importlib.util.find_spec("rdflib") is None:
            raise ImportError("rdflib is required to use OntologyService")
        from rdflib import Namespace

        self._graph = load_graph("mas")
        self._cache_subclasses = {}

        # Auto-discover namespaces
        self._namespaces = {}
        for prefix, uri in self._graph.namespaces():
            self._namespaces[prefix] = Namespace(uri)

        # Ensure critical namespaces
        if "mas" not in self._namespaces:
            self._namespaces["mas"] = Namespace(
                "http://www.semanticweb.org/cisco/ontologies/2024/9/mas-ontology#"
            )

        self.mas = self._namespaces["mas"]

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = OntologyService()
        return cls._instance

    def expand_curie(self, curie: str) -> str:
        """Expand 'mas:Session' to full URI string."""
        if ":" in curie:
            prefix, local = curie.split(":", 1)
            if prefix in self._namespaces:
                return str(self._namespaces[prefix][local])
        return curie

    def get_subclasses_of(self, parent_curie: str) -> set[str]:
        """
        Returns set of CURIEs that are transitive subclasses of parent_curie.
        Includes parent_curie itself.
        """
        if parent_curie in self._cache_subclasses:
            return self._cache_subclasses[parent_curie]

        parent_uri = self.expand_curie(parent_curie)

        query = """
        SELECT ?sub WHERE { ?sub rdfs:subClassOf* ?parent }
        """

        results = set()
        try:
            # We must pass URIRef to initBindings
            import rdflib

            parent_node = rdflib.URIRef(parent_uri)

            for row in self._graph.query(query, initBindings={"parent": parent_node}):
                uri = str(row.sub)
                # Compress back to CURIE
                matched = False
                for prefix, ns in self._namespaces.items():
                    ns_str = str(ns)
                    if uri.startswith(ns_str):
                        results.add(f"{prefix}:{uri[len(ns_str) :]}")
                        matched = True
                        break
                if not matched:
                    results.add(uri)
        except Exception as exc:  # noqa: BLE001
            warnings.warn(f"OntologyService query error: {exc}", stacklevel=2)

        # Ensure reflexive
        results.add(parent_curie)

        self._cache_subclasses[parent_curie] = results
        return results
