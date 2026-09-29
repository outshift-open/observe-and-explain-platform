# OXP Ontology Package Structure

```
oxp-ontology/
│
├── README.md                     # Main repository documentation
├── REPOSITORY_STRUCTURE.md       # This file
├── CHANGELOG.md                  # Release history
├── DOCS_DEPLOYMENT.md            # How the GitHub Pages docs site is built
├── index.md                      # Landing-page copy for the docs site
├── VERSION                       # Per-component version manifest (mas/semantic/metrics/analysis/insight)
├── Taskfile.yml                  # Task automation (test, validate, version, build)
├── Makefile                      # Doc/model/shape generation targets
│
├── src/oxp_ontology/              # Python package + ontology sources
│  ├── __init__.py                # get_ontology_path(), load_graph(), OntologyService, re-exports validation/verification API
│  ├── validation.py              # Structural + payload validation (validate_bundled_ontologies, validate_session_payload, ...)
│  ├── verification.py            # SHACL-based KG object verification (verify_kg_object)
│  ├── mas-ontology.ttl           # Core execution schema (Sessions, Agents, Calls, State/Transition trajectory)
│  ├── semantic-ontology.ttl      # Embedding layer (independently versioned)
│  ├── metrics-ontology.ttl       # Metrics ontology (Metric/MetricResult, templates)
│  ├── analysis-ontology.ttl      # Post-hoc group analysis reports
│  ├── insight-ontology.ttl       # Rendered, catalog-templated insights
│  ├── mas-shapes-custom.ttl      # Hand-maintained SHACL (SPARQL-based multi-node constraints) — committed
│  ├── mas-shapes.ttl             # Auto-generated SHACL scaffolding — gitignored, NOT committed
│  └── models/                    # Pydantic KG node/edge models
│     ├── __init__.py            # Flat re-export: `from oxp_ontology.models import AgentCall`
│       ├── base.py                # KGBase/KGNode/KGEdge — hand-written, the only committed file here
│       ├── nodes/                 # Generated from the ontology — gitignored, NOT committed
│       └── edges/                 # Generated from the ontology — gitignored, NOT committed
│
├── docs/                          # Versioning/release docs (not the deployed GitHub Pages site — that's docs.yml output, gitignored/pages-only)
│  ├── VERSIONING.md              # Per-component semantic versioning + RC strategy
│  └── RELEASE_PROCESS.md         # Release workflow (PR -> merge -> tag -> publish)
│
├── scripts/                       # Utility Scripts
│  ├── validate_ttl.py            # CLI wrapper around oxp_ontology.validation
│  ├── version_manager.py         # Per-component version get/bump/set (mas, semantic, metrics, analysis, insight)
│  ├── generate_models.py         # Generates src/oxp_ontology/models/{nodes,edges}/ from the ontology
│  ├── generate_shacl_shapes.py   # Generates mas-shapes.ttl from the ontology
│  ├── inject_shacl_into_properties.py  # Migration tool: dual-types owl:*Property declarations as sh:PropertyShape
│  ├── generate_all_docs.sh       # Local, single-ontology (mas-only) Widoco+WebVOWL+LODE build for previewing
│  ├── generate_webvowl_json.py   # WebVOWL JSON for mas-ontology.ttl specifically
│  ├── generate_webvowl_json_generic.py  # WebVOWL JSON for any single ontology file (used by CI, per-ontology)
│  ├── generate_webvowl_json_merged.py   # WebVOWL JSON merging multiple ontology files into one graph
│  └── generate_lode_html.py       # Local LODE-style HTML generator (lightweight alternative to the LODE web service)
│
├── tests/                         # Python Tests
│  ├── test_package.py            # Package installation + ontology loading
│  ├── test_models.py             # Generated Pydantic KG model tests
│  └── test_verification.py       # SHACL verification tests
│
├── widoco/                        # Committed static export (index.html only — no widoco.jar committed; CI downloads+caches the JAR)
```

## Bundled Ontology Components

As of `v2.0.0`, the bundled set is exactly five ontology files, all merged under the shared `mas:` namespace (the file split is for readability, not independent namespace identity):

| Component | File | Versioning |
|-----------|------|------------|
| `mas` | `mas-ontology.ttl` | Lockstep with metrics/analysis/insight; tracked in `pyproject.toml` |
| `semantic` | `semantic-ontology.ttl` | Independent |
| `metrics` | `metrics-ontology.ttl` | Lockstep |
| `analysis` | `analysis-ontology.ttl` | Lockstep |
| `insight` | `insight-ontology.ttl` | Lockstep |

## Quick Commands

```bash
# Run tests
task test

# Validate ontology syntax
task validate-ttl

# Generate KG models / SHACL shapes
task build-models
make generate-shapes

# Generate documentation locally (single-ontology preview)
./scripts/generate_all_docs.sh

# Bump version (RC)
task version-bump-rc
```

## Documentation Websites

- **Main docs**: https://outshift-open.github.io/oxp-ontology/
- **MAS Widoco**: https://outshift-open.github.io/oxp-ontology/mas/widoco/
- **MAS WebVOWL**: https://outshift-open.github.io/oxp-ontology/mas/webvowl/
- **Metrics Widoco**: https://outshift-open.github.io/oxp-ontology/metrics/widoco/
- **Metrics WebVOWL**: https://outshift-open.github.io/oxp-ontology/metrics/webvowl/

See [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md) for how these are generated.
