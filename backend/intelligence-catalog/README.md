# Intelligence Catalog

Central repository for curated Insight templates consumed by the Poirot platform.

Templates are stored in version-controlled JSON files and loaded into memory at application startup.
The DEM Intelligence module validates templates and generates Insight nodes when queries are executed against the knowledge graph.

## Structure

```
intelligence-catalog/
├── insight-templates/     # JSON files defining insight patterns and rendering templates
├── recommendations/       # (future) Remediation suggestions linked to insights
└── root-causes/           # (future) Root-cause patterns linked to insights
```

## Adding a new InsightTemplate

Create a JSON file under `insight-templates/`. File name should be kebab-case and descriptive.

### Required fields
| Field | Description |
|---|---|
| `nameTemplate` | Insight title template; use `$variable` placeholders to substitute query results |
| `descriptionTemplate` | Insight body template; use `$variable` placeholders to substitute query results |
| `kgQuery` | Cypher query that detects the pattern and returns the variables used in templates |

### Optional fields
| Field | Description |
|---|---|
| `labels` | List of tag strings (e.g. `["Performance", "Reliability"]`); supports `$variable` placeholders |
| `scope` | Execution scope: must be one of `Session`, `Agent`, `MAS`, or `SemanticGroup` |
| `priority` | Priority level: string like `P1`, `P2`, `P3` or numeric `0`–`10` |
| `targetNodeId` | UUID of a KG node to attach generated insights to |

### Validation Rules

1. **Variable Matching**: All `$variable` placeholders in `nameTemplate`, `descriptionTemplate`, `labels`, `targetNodeId`, and `priority` must appear in the Cypher query's `RETURN` clause.
2. **Scope Validation**: If specified, `scope` must be one of: `Session`, `Agent`, `MAS`, or `SemanticGroup`.
3. **Cypher Syntax**: The `kgQuery` must be a valid Cypher query with a `RETURN` clause that returns all required template variables.

### Example

```json
{
  "nameTemplate": "High latency detected on $service",
  "descriptionTemplate": "Service $service has average latency of $latencyMs ms (threshold: $thresholdMs ms)",
  "kgQuery": "MATCH (s:Service {name: $serviceName}) RETURN s.name as service, round(s.avgLatency) as latencyMs, $threshold as thresholdMs",
  "labels": ["Performance", "$severity"],
  "scope": "Session",
  "priority": "P1"
}
```

## Loading & Generation

**Loading** (`dem.intelligence.loader.load_templates_from_disk`):
- Reads all JSON files from `intelligence-catalog/insight-templates/`
- Validates each template (scope, variable matching)
- Returns list of `InsightTemplateModel` instances cached in memory

**Generation** (`IntelligenceWrapper.generate_insights`):
- Executes each template's Cypher query against the knowledge graph
- For each query result row, creates an `InsightNode` by rendering templates with row variables
- Async execution with configurable concurrency (default: 8 concurrent queries)
