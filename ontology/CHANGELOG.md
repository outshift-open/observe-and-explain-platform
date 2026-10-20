# Changelog

All notable changes to the OXP Ontology will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versioning starts at `1.0.0` with this open-source release.

## [1.0.6] - 2026-10-20

### Added

- `analysis-ontology.ttl`: `CognitiveFailureReport`, one detection of a cognitive failure from the challenges
  taxonomy in a session: `code` (the challenge's code, e.g. `IR-1`), `confidence` (`low` | `medium` | `high`) and
  `reasoning`. It is linked to its `Session` by `reportsOn` and, when the failure happened in one call, to that call
  by the new `atCall`. `reportsOn` and `reportedAt` now also apply to it.
- `analysis-ontology.ttl`: `CognitionProtocolReport` (which Cognition protocols were enabled and which activated in a session, as
  `protocolsEnabled` / `protocolsActivated` lists) and `CognitionProtocolExecutionReport` (how one protocol went in
  a session: `protocol`, the agents and skills that had it and used it, `metricCount`), both linked to their
  `Session` by `reportsOn`. Reports carry `sessionId` and `reportedAt`.
- `metrics-ontology.ttl`: `measures` may now target a `CognitionProtocolExecutionReport`, so a protocol's evaluation
  metrics are `MetricResult`s attached to its report.
- `mas:multiValued` annotation: marks a datatype property as a list. `scripts/generate_models.py` types such a
  property as a list of its range.
- `hatch_build.py`: a build hook that generates `mas-shapes.ttl` and the KG models when the package is built from
  a source checkout, so `{ git = "...", subdirectory = "ontology" }` and `pip install ./ontology` give a complete
  package, not only the CI-built wheel. Built from an sdist (scripts absent, files already inside) it does nothing.

## [1.0.5] - 2026-10-12

### Added

- `metrics-ontology.ttl`: required `timestamp` (`xsd:dateTime`) on `MetricResult`, the time the observation was computed, so a metric's results can be ordered and bucketed over time.

## [1.0.4] - 2026-10-12

### Added

- `metrics-ontology.ttl`: optional evaluation-cost properties on `MetricResult`, for metrics computed with an
  LLM: `evaluationModel`, `evaluationPromptTokenCount`, `evaluationCompletionTokenCount`,
  `evaluationTotalTokenCount` and `evaluationCost` (an estimate from token counts and list price).

## [1.0.3] - 2026-10-12

### Added

- `semantic-ontology.ttl`: `TrajectoryContext` semantic element holding the trajectory context a
  `Transition` contributed to its session, one property per constituent (`evidence`,
  `claims`, `intents`, `workUnits`, `provenanceLinks`,
  `coordinationEvents`, `flags`, `finalAnswer`), and the `hasContext` link from
  `Transition`, so the running context can be rebuilt from the trajectory.

## [1.0.2] - 2026-10-05

### Fixed

- `semantic-ontology.ttl`: `containsSemanticGroup` had its `sh:path` and `rdfs:domain`/`rdfs:range`
  reversed (copy-pasted from `containsSession`). Corrected to `domain mas:MAS`, `range
  mas:SemanticGroup`, `sh:path :containsSemanticGroup`, matching its own description ("MAS contains
  this SemanticGroup").

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
