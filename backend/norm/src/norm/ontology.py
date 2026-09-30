#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Resolve ontology TTL paths for KG normalization and validation.

Resolution order for each TTL:
1. Explicit ``config_path`` argument (user override).
2. External ``oxp_ontology`` package (canonical source).

This module intentionally avoids local/vendored ontology copies so there is a
single ontology source of truth.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def _get_ontology_path(name: str) -> str:
    """Resolve an ontology TTL path from the oxp_ontology package."""
    try:
        from oxp_ontology import get_ontology_path  # type: ignore[import]

        return get_ontology_path(name)
    except ImportError as exc:
        raise ImportError("oxp_ontology is required by norm to resolve ontology TTL files") from exc


def resolve_mas_ontology_path(config_path: Optional[str] = None) -> Path:
    """Return the path to ``mas-ontology.ttl``.

    Tries: explicit config_path → external oxp_ontology.
    """
    if config_path:
        path = Path(config_path).expanduser().resolve()
        if path.exists():
            return path
        raise FileNotFoundError(f"ontology_path not found: {config_path}")

    return Path(_get_ontology_path("mas-ontology"))


def resolve_mas_shapes_path() -> Optional[Path]:
    """Return the path to ``mas-shapes.ttl`` (generated SHACL class scaffolding)."""
    try:
        return Path(_get_ontology_path("mas-shapes"))
    except FileNotFoundError:
        logger.warning("mas-shapes.ttl not found in oxp_ontology")
        return None


def resolve_mas_shapes_custom_path() -> Optional[Path]:
    """Return the path to ``mas-shapes-custom.ttl`` (hand-maintained SHACL rules).

    Loaded alongside ``mas-shapes.ttl`` — never in isolation: the generated
    file only emits bare ``sh:property`` references to inline
    ``sh:PropertyShape`` declarations on properties in ``mas-ontology.ttl``
    itself, and ``mas-shapes-custom.ttl`` layers a handful of cross-node
    SHACL rules (SPARQL-based) on top of both.
    """
    try:
        return Path(_get_ontology_path("mas-shapes-custom"))
    except FileNotFoundError:
        logger.warning("mas-shapes-custom.ttl not found in oxp_ontology")
        return None


def resolve_kg_ontology_paths() -> List[Path]:
    """Return all TTL paths for the combined KG validation graph.

    Just ``mas-ontology.ttl`` — norm's execution/structural/trajectory
    layer normalization has no dependency on the semantic/metrics/analysis/
    insight ontologies (those cover downstream analysis, not normalization).
    Always resolves — never returns empty (raises if mas-ontology.ttl is
    missing).
    """
    return [resolve_mas_ontology_path()]


def resolve_all_ontology_paths() -> List[Path]:
    """Return every bundled ontology TTL path (mas + semantic/metrics/analysis/insight).

    Needed specifically for the SHACL *shapes* graph: the generated
    ``mas-shapes.ttl`` declares class shapes (with bare ``sh:property``
    references) for classes across every ontology module, not just
    ``mas-ontology.ttl`` — e.g. ``AnomalyReportShape`` references
    ``mas:isAnomalous``, declared in ``analysis-ontology.ttl``. Loading only
    ``mas-ontology.ttl`` leaves those references unresolved, which pyshacl
    rejects as "not a well-formed SHACL PropertyShape" while compiling the
    shapes graph — before it even reaches norm's own data. Mirrors
    ``oxp_ontology.verification._shapes_graph()``, which loads the same set
    for the same reason.
    """
    try:
        from oxp_ontology import ONTOLOGY_FILES  # type: ignore[import]
    except ImportError as exc:
        raise ImportError("oxp_ontology is required by norm to resolve ontology TTL files") from exc

    paths: List[Path] = []
    for name in ONTOLOGY_FILES:
        try:
            paths.append(Path(_get_ontology_path(name)))
        except FileNotFoundError:
            logger.warning("Ontology TTL %s not found in oxp_ontology", name)
    return paths
