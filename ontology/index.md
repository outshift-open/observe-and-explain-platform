# OXP Ontology Documentation

🌐 **Live Documentation**: [https://outshift-open.github.io/observe-and-explain-platform/](https://outshift-open.github.io/observe-and-explain-platform/)

The deployed site covers all five bundled ontologies — **MAS**, **Metrics**, **Semantic**, **Analysis**, and **Insight** — each with three documentation formats, plus the [backend documentation](https://outshift-open.github.io/observe-and-explain-platform/backend/).

## 📚 Documentation Formats

Each ontology (`mas`, `metrics`, `semantic`, `analysis`, `insight`) gets its own set, at `<ontology>/widoco/`, `<ontology>/webvowl/`, and `<ontology>/lode/` — e.g. [MAS Widoco](https://outshift-open.github.io/observe-and-explain-platform/mas/widoco/index-en.html):

### 1. Widoco (Standard)
W3C-compliant OWL documentation with cross-references and namespace details.

### 2. WebVOWL (Interactive)
Interactive graph visualization: zoom, pan, node filtering, and visual exploration of the ontology structure.

### 3. LODE (Lightweight)
Minimal-styling, fast-loading HTML documentation.

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
    └── deploy-docs-multi.yml   # Auto-deploy to GitHub Pages (all ontologies)
```

See [REPOSITORY_STRUCTURE.md](REPOSITORY_STRUCTURE.md) for the full breakdown and [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md) for how the deployment pipeline works.

## 🤝 Contributing

Documentation auto-deploys on every push to `main`. To contribute:

1. Modify the relevant `*-ontology.ttl` file
2. Preview locally: `./scripts/generate_all_docs.sh`
3. Commit and push
4. GitHub Actions deploys automatically

See [DOCS_DEPLOYMENT.md](DOCS_DEPLOYMENT.md) for details.
