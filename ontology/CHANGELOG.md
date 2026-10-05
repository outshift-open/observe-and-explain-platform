# Changelog

All notable changes to the OXP Ontology will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning starts at `1.0.0` with this open-source release.

## [1.0.1] - 2026-10-05

### Added

- `semantic-ontology.ttl`: `containsSemanticGroup` link from `MAS` to `SemanticGroup`.

### Fixed

- `mas-ontology.ttl`: optional `mas:success` boolean on `ExecutionElement`, so `Session` and every
  `*Call` model accepts the success flag already set by `norm`.

## [1.0.0] - 2026-09-30

### Added

Initial open-source release of the OXP Ontology.

- Five bundled Turtle ontologies, all under a single `mas:` namespace:
  - `mas-ontology.ttl` — core execution schema: structural types (`MAS`, `Agent`, `LLM`, `Tool`,
    `Processing`), their execution instances, and the normalized State/Transition trajectory.
  - `semantic-ontology.ttl` — embedding layer linking State/Execution nodes to embeddings.
  - `metrics-ontology.ttl` — Metric/MetricResult definition-observation split.
  - `analysis-ontology.ttl` — group-scoped analysis reports (consistency, anomaly, normal
    behaviour) computed over a `SemanticGroup` of sessions.
  - `insight-ontology.ttl` — rendered, catalog-templated insights attached to a target KG node.
- SHACL shapes: hand-maintained multi-node/conditional constraints in `mas-shapes-custom.ttl`,
  plus `scripts/generate_shacl_shapes.py` to scaffold class-level shapes from the ontology files.
- `oxp-ontology` Python package:
  - `get_ontology_path()` / `load_graph()` for programmatic access to the bundled files.
  - `validate_bundled_ontologies()` — structural validation of the ontology files themselves.
  - `verify_kg_object()` — SHACL-based verification of a single constructed KG node/edge object.
  - Generated Pydantic KG node/edge models (`models/nodes/`, `models/edges/`) reflecting each
    property's SHACL requirement tier (mandatory / recommended / optional).
- Per-component semantic versioning (`mas`, `semantic`, `metrics`, `analysis`, `insight`), with
  `mas`/`metrics`/`analysis`/`insight` kept in lockstep and `semantic` versioned independently —
  see [docs/VERSIONING.md](docs/VERSIONING.md).
- Documentation published to [outshift-open.github.io/oxp-ontology](https://outshift-open.github.io/oxp-ontology/)
  (Widoco, WebVOWL, LODE) for the `mas` and `metrics` ontologies, via CI on every push to `main`.
