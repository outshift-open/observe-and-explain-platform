# Intelligence Catalog

Central, version-controlled repository of Insight templates — JSON files that pair a Cypher query over the knowledge graph with a rendering template for the resulting `Insight` node.

**Source:** [`intelligence-catalog`](https://github.com/outshift-open/observe-and-explain-platform/tree/main/backend/intelligence-catalog)

## Overview

Unlike the other backend components, this isn't a Python library — it's a data catalog: plain JSON template files, loaded from disk at runtime. It's consumed in two steps:

1. **Loading** — `dem.intelligence.loader.load_templates_from_disk` (`backend/dem/src/dem/intelligence/loader.py`) walks `insight-templates/**/*.json`, parses each file into an `InsightTemplateModel` (`backend/dem/src/dem/intelligence/template_model.py`), and validates it: `scope` must be one of `Session`, `Agent`, `MAS`, `SemanticGroup`, and every `$variable` placeholder used in `nameTemplate`/`descriptionTemplate`/`labels`/`priority`/`targetNodeId` must also appear in the `kgQuery`'s `RETURN` clause. Invalid templates are logged and skipped, not fatal.
2. **Generation** — the [intelligence-worker](../workers/intelligence-worker.md)'s `IntelligenceWrapper.generate_insights` (`backend/workers/intelligence-worker/src/intelligence_worker/wrapper/intelligence_wrapper.py`) runs each template's `kgQuery` against the knowledge graph; for every result row it substitutes the row's variables into the templates to build an `Insight` node (deduplicated by a hash of template id + target node + rendered name) and persists the batch to the KG.

### Repository structure

```
intelligence-catalog/
├── insight-templates/
│   ├── group/      # SemanticGroup-scoped templates (3 today)
│   └── session/    # Session-scoped templates (6 today)
├── recommendations/  # empty (.gitkeep) — reserved for future remediation content
└── root-causes/      # empty (.gitkeep) — reserved for future root-cause patterns
```

`recommendations/` and `root-causes/` are placeholders for now; nothing reads from them yet.

## Template format

Each `insight-templates/**/*.json` file is one `InsightTemplateModel`:

| Field | Required | Description |
|---|---|---|
| `nameTemplate` | yes | Insight title, with `$variable` placeholders |
| `descriptionTemplate` | yes | Insight body, with `$variable` placeholders |
| `kgQuery` | yes | Cypher query; either a plain string or (as used by every template today) a JSON array of lines, joined with `\n` by the loader |
| `labels` | no | List of tag strings, may contain placeholders |
| `scope` | no | One of `Session`, `Agent`, `MAS`, `SemanticGroup` |
| `priority` | no | e.g. `"P1"`–`"P3"`, or itself a `$variable` resolved from the query |
| `targetNodeId` | no | KG node id the generated `Insight` attaches to, usually a `$variable` |

Real example (`insight-templates/group/execution-graph-inconsistency-group.json`):

```json
{
  "nameTemplate": "Unreliable execution patterns in group \"$groupName\"",
  "descriptionTemplate": "Traces about \"$groupName\" have unreliable execution patterns (consistency=$meanValue, below the threshold $threshold).",
  "kgQuery": [
    "MATCH (sg:SemanticGroup)-[:hasConsistencyReport]->(cr:ConsistencyReport)",
    "WHERE cr.dataType = 'graph'",
    "WITH sg, cr, 0.70 AS threshold, toFloat(cr.mean) AS consistencyValue",
    "WHERE consistencyValue < threshold",
    "RETURN sg.id AS groupId, sg.groupName AS groupName,",
    "  round(consistencyValue, 4) AS meanValue, round(threshold, 2) AS threshold"
  ],
  "labels": ["Reliability"],
  "scope": "SemanticGroup",
  "priority": "P2",
  "targetNodeId": "$groupId"
}
```

Session-scoped templates follow the same shape, reading from `Metric`, `AnomalyReport`, and `ConsistencyReport` nodes attached to a `Session`/`SemanticGroup` (see `insight-templates/session/*.json`).

## Adding a new template

1. Add a kebab-case JSON file under `insight-templates/group/` or `insight-templates/session/`.
2. Make sure every `RETURN`-clause alias needed by the templates/labels/priority/targetNodeId is present — the loader rejects templates where a `$variable` isn't returned by the query.
3. No build step is required: the catalog is read from disk at worker startup (`catalog_root` passed to `IntelligenceWrapper`), so a new template only needs redeploying/restarting the [intelligence-worker](../workers/intelligence-worker.md).

See also [analysis](analysis.md) for the `ConsistencyReport`/`AnomalyReport` nodes these templates query against.
