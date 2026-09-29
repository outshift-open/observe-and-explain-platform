# OXP Ontology Documentation

🌐 **Live Documentation**: [https://outshift-open.github.io/oxp-ontology/](https://outshift-open.github.io/oxp-ontology/)

The deployed site currently covers two of the five bundled ontologies — **MAS** and **Metrics** — each with three documentation formats.

## 📚 Documentation Formats

### 1. [MAS Widoco](https://outshift-open.github.io/oxp-ontology/mas/widoco/index-en.html) / [Metrics Widoco](https://outshift-open.github.io/oxp-ontology/metrics/widoco/index-en.html) (Standard)
W3C-compliant OWL documentation with cross-references and namespace details.

### 2. [MAS WebVOWL](https://outshift-open.github.io/oxp-ontology/mas/webvowl/) / [Metrics WebVOWL](https://outshift-open.github.io/oxp-ontology/metrics/webvowl/) (Interactive)
Interactive graph visualization: zoom, pan, node filtering, and visual exploration of the ontology structure.

### 3. [MAS LODE](https://outshift-open.github.io/oxp-ontology/mas/lode/) / [Metrics LODE](https://outshift-open.github.io/oxp-ontology/metrics/lode/) (Lightweight)
Minimal-styling, fast-loading HTML documentation.

`semantic`, `analysis`, and `insight` ontologies are bundled in the Python package and validated in CI, but aren't published to this site yet.

## 🚀 Quick Start

```bash
# Generate a local, single-ontology (mas-only) preview
./scripts/generate_all_docs.sh

# Serve locally
python3 -m http.server 8000 --directory docs
# Open: http://localhost:8000
```

## 📦 Repository Structure

```
.
├── src/oxp_ontology/
│   ├── mas-ontology.ttl        # Core execution schema
│   ├── semantic-ontology.ttl   # Embedding layer
│   ├── metrics-ontology.ttl    # Metrics
│   ├── analysis-ontology.ttl   # Post-hoc analysis
│   └── insight-ontology.ttl    # Rendered insights
├── scripts/
│   ├── generate_webvowl_json_generic.py  # Per-ontology WebVOWL JSON (used by CI)
│   ├── generate_lode_html.py             # Lightweight LODE-style HTML
│   └── generate_all_docs.sh              # Local mas-only preview build
└── .github/workflows/
    └── deploy-docs-multi.yml   # Auto-deploy to GitHub Pages (mas + metrics)
```

See [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) for the full breakdown and [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md) for how the deployment pipeline works.

## 🤝 Contributing

Documentation auto-deploys on every push to `main`. To contribute:

1. Modify the relevant `*-ontology.ttl` file
2. Preview locally: `./scripts/generate_all_docs.sh`
3. Commit and push
4. GitHub Actions deploys automatically

See [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md) for details.
