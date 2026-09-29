# OXP Ontology

**Multi-Agent System (MAS) Telemetry Ontology** for observability and governance of multi-agent systems.

## 📖 Documentation

The complete documentation for the OXP Ontology Collection is available at: **[https://outshift-open.github.io/oxp-ontology/](https://outshift-open.github.io/oxp-ontology/)**

| Ontology | Description | Documentation | Visualization |
|----------|-------------|---------------|----------------|
| **MAS** | Core execution schema: structural types (MAS, Agent, LLM, Tool, Processing), their execution instances, and the normalized State/Transition trajectory | [Widoco](https://outshift-open.github.io/oxp-ontology/mas/widoco/) | [WebVOWL](https://outshift-open.github.io/oxp-ontology/mas/webvowl/) |
| **Metrics** | Metric/MetricResult definition-observation split, score nodes, templates | [Widoco](https://outshift-open.github.io/oxp-ontology/metrics/widoco/) | [WebVOWL](https://outshift-open.github.io/oxp-ontology/metrics/webvowl/) |

`semantic`, `analysis`, and `insight` are bundled in the Python package and validated in CI, but don't have a published Widoco/WebVOWL site yet — only `mas` and `metrics` are deployed today. See [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md).

## 🔗 Namespace

All five bundled ontologies share a single namespace — there's no separate prefix per file:

```turtle
@prefix mas: <https://outshift-open.github.io/oxp-ontology/mas#> .
```

## 📥 Download

- **MAS**: [mas-ontology.ttl](https://raw.githubusercontent.com/outshift-open/oxp-ontology/main/src/oxp_ontology/mas-ontology.ttl)
- **Semantic (embedding layer)**: [semantic-ontology.ttl](https://raw.githubusercontent.com/outshift-open/oxp-ontology/main/src/oxp_ontology/semantic-ontology.ttl)
- **Metrics**: [metrics-ontology.ttl](https://raw.githubusercontent.com/outshift-open/oxp-ontology/main/src/oxp_ontology/metrics-ontology.ttl)
- **Analysis**: [analysis-ontology.ttl](https://raw.githubusercontent.com/outshift-open/oxp-ontology/main/src/oxp_ontology/analysis-ontology.ttl)
- **Insight**: [insight-ontology.ttl](https://raw.githubusercontent.com/outshift-open/oxp-ontology/main/src/oxp_ontology/insight-ontology.ttl)
- **Custom SHACL shapes**: [mas-shapes-custom.ttl](https://raw.githubusercontent.com/outshift-open/oxp-ontology/main/src/oxp_ontology/mas-shapes-custom.ttl) — the auto-generated `mas-shapes.ttl` is not committed (see [Development](#️-development))

## Repository Structure

- **[src/oxp_ontology/](src/oxp_ontology/)**: Ontology source files (Turtle) and the `oxp-ontology` Python package
- **[docs/](docs/)**: Versioning and release-process documentation
- **[scripts/](scripts/)**: Doc/model/shape generation and versioning utilities

See [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) for the full file-by-file breakdown.

## 📚 Overview

The bundled ontology set is exactly five Turtle files, all under the `mas:` namespace:

### 1. `mas-ontology.ttl` — Core Execution Schema
Structural types, their execution instances, and the normalized trajectory each execution produces, rooted in a common `:Element` base class:
- **Structural**: `MAS`, `Agent`, `Capability`, `LLM`, `Tool`, `Processing`
- **Execution**: `Session`, `MASCall`, `AgentCall`, `CapabilityCall`, `LLMCall`, `ToolCall`, `ProcessingCall`
- **Trajectory (normalized layer)**: `State`, `Transition`

### 2. `semantic-ontology.ttl` — Embedding Layer
Semantic embedding layer for MAS trajectories: `SemanticElement`, `Embedding`, and links from State/Execution nodes to embeddings. Versioned independently from the other four ontologies — see [docs/VERSIONING.md](docs/VERSIONING.md).

### 3. `metrics-ontology.ttl` — Metrics
Metric/MetricResult definition-observation split, integrated with `mas-ontology.ttl` via `hasMetric`. Concrete metric catalog instances live outside of this package.

### 4. `analysis-ontology.ttl` — Post-hoc Analysis
Group-scoped analysis reports (consistency, anomaly, normal-behaviour) computed over a `SemanticGroup` of sessions — an `mas:AnalysisElement` companion to `mas-ontology.ttl`.

### 5. `insight-ontology.ttl` — Rendered Insights
Catalog-templated insights attached to a target KG node (MAS, Agent, Session, SemanticGroup), rendered from a KG query plus an `InsightTemplate`. Also an `mas:AnalysisElement`.

### SHACL Shapes
- `mas-shapes-custom.ttl` (committed) — hand-maintained constraints the generator can't express (SPARQL-based multi-node rules, conditional "if A then B" checks)
- `mas-shapes.ttl` (**not committed**) — class-level `sh:NodeShape` scaffolding, auto-generated from the ontology files by `scripts/generate_shacl_shapes.py` / `make generate-shapes`

## 🚀 Quick Start

### Install the package

```bash
# Clone the repository
git clone https://github.com/outshift-open/observe-and-explain-platform.git
cd observe-and-explain-platform/ontology

# Install the Python package
pip install oxp-ontology
```

### Import in your own ontology

```turtle
@prefix mas: <https://outshift-open.github.io/oxp-ontology/mas#> .
@prefix ex: <http://example.org/myproject#> .

ex:myAgent a mas:Agent ;
    mas:executes ex:myTask .

ex:myMAS a mas:MAS ;
    mas:hasAgent ex:myAgent .
```

### Query with SPARQL

```sparql
PREFIX mas: <https://outshift-open.github.io/oxp-ontology/mas#>

SELECT ?agent ?task WHERE {
    ?agent a mas:Agent ;
           mas:executes ?task .
}
```

## 🛠️ Development

### Python Package

```bash
pip install oxp-ontology
```

Access ontologies programmatically:

```python
from oxp_ontology import get_ontology_path, load_graph

# Get file path (valid names: mas, semantic, metrics, analysis, insight,
# mas-shapes, mas-shapes-custom)
mas_path = get_ontology_path("mas")
metrics_path = get_ontology_path("metrics")

# Load into an rdflib graph
g = load_graph("mas")
```

The package also exposes validation and SHACL-verification helpers:

```python
from oxp_ontology import validate_bundled_ontologies, verify_kg_object

# Structural validation of the bundled TTL files
report = validate_bundled_ontologies()

# SHACL-based verification of a KG object against mas-shapes(-custom).ttl
verify_kg_object(my_kg_dict)
```

### Generate KG models and SHACL shapes

The Pydantic KG node/edge models (`src/oxp_ontology/models/nodes/`, `models/edges/`) and `mas-shapes.ttl` are generated from the ontology, not committed:

```bash
task build-models          # or: make generate-models
make generate-shapes        # scaffolds mas-shapes.ttl from the ontology
```

CI (`.github/workflows/test.yml`) regenerates both before running tests.

### Run tests

```bash
task test              # uv run pytest -v
task test-coverage      # pytest with coverage report
task validate-ttl       # validate TTL syntax/structure
```

### Version management

Each ontology component (`mas`, `semantic`, `metrics`, `analysis`, `insight`) is versioned independently in the `VERSION` manifest and each file's `owl:versionInfo`; `mas`/`metrics`/`analysis`/`insight` are kept in lockstep, `semantic` moves on its own. `pyproject.toml` tracks the `mas` version.

```bash
task version                 # current mas version
task version-full            # with commit SHA (for RC builds)
task version-bump-rc          # rc0 -> rc1
task version-bump-patch       # remove RC, increment patch
task version-bump-minor       # remove RC, increment minor
task version-bump-major       # remove RC, increment major
task version-set -- 1.2.0-rc0 # set an exact version
task version-check            # verify VERSION <-> pyproject.toml consistency
```

See [docs/VERSIONING.md](docs/VERSIONING.md) for the complete strategy.

### Validate ontology

```bash
task validate-ttl                                    # rdflib-based structural validation
rapper -i turtle src/oxp_ontology/mas-ontology.ttl > /dev/null   # Raptor RDF parser
```

### Generate documentation locally

```bash
./scripts/generate_all_docs.sh
```

This generates a single-ontology Widoco/WebVOWL/LODE build for `mas-ontology.ttl` under `docs/`, useful for a quick local preview. It is **not** what CI publishes — the deployed site is built per-ontology (currently `mas` and `metrics`) by `.github/workflows/deploy-docs-multi.yml`. See [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md) for the full picture.

### Legacy visualization tools

- **[TIB WebVOWL](https://service.tib.eu/webvowl/#file=mas.ttl)** - upload your file
- **[Protégé](https://protege.stanford.edu/)** - desktop editor with reasoner support

## 🧪 Testing & Quality

This repository includes:
- **Unit tests** for the Python package (pytest, matrix-tested on Python 3.10-3.13)
- **Ruff** lint + format check
- **TTL validation** (syntax, structure, and cross-file `owl:versionInfo` consistency for the lockstep components)
- **CI/CD** on every PR and push to `main`

See [`.github/workflows/test.yml`](.github/workflows/test.yml).

## 📦 Versioning Strategy

Semantic versioning with release candidates, tracked per-component:
- **RC versions**: `1.0.0-rc0+g<commit-sha>` (commit SHA for traceability)
- **Final releases**: `1.0.0` (clean, no metadata)

See [docs/VERSIONING.md](docs/VERSIONING.md) for the versioning strategy and [docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md) for the full release workflow.

## 📄 License

The bundled ontology files declare `dcterms:license <https://opensource.org/licenses/Apache-2.0>` in their headers.

---

Documentation deploys automatically on push to `main` via `.github/workflows/deploy-docs-multi.yml`. The Python package publishes via `.github/workflows/publish-package.yml` on a `v*` tag push or manual dispatch.
