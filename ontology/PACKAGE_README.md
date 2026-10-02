# oxp-ontology

**Multi-Agent System (MAS) Execution Ontology** — RDF/OWL vocabulary and Python
helpers for describing, validating, and querying multi-agent system telemetry
as a knowledge graph.

Part of the [Observe and eXplain Platform](https://github.com/outshift-open/observe-and-explain-platform).

## What's included

Five Turtle ontologies under a single `mas:` namespace:

| Ontology | Covers |
|----------|--------|
| **mas** | Core schema: `MAS`, `Agent`, `LLM`, `Tool`, `Processing`, their execution instances, and the normalized State/Transition trajectory |
| **metrics** | Metric/MetricResult definitions and observations |
| **semantic** | Embedding layer linking trajectory nodes to vector embeddings |
| **analysis** | Group-scoped analysis reports (consistency, anomaly, normal behaviour) |
| **insight** | Catalog-templated insights rendered onto a knowledge-graph node |

Plus SHACL shapes (`mas-shapes.ttl`, `mas-shapes-custom.ttl`) for validating
knowledge-graph instances against the ontology.

## Install

```bash
pip install oxp-ontology
```

## Usage

### Import the ontology in your own RDF

```turtle
@prefix mas: <https://outshift-open.github.io/oxp-ontology/mas#> .
@prefix ex: <http://example.org/myproject#> .

ex:myAgent a mas:Agent ;
    mas:executes ex:myTask .

ex:myMAS a mas:MAS ;
    mas:hasAgent ex:myAgent .
```

### Access bundled files and load graphs

```python
from oxp_ontology import get_ontology_path, load_graph

# Valid names: mas, semantic, metrics, analysis, insight,
# mas-shapes, mas-shapes-custom
mas_path = get_ontology_path("mas")

g = load_graph("mas")
```

### Validate and verify

```python
from oxp_ontology import validate_bundled_ontologies, verify_kg_object

# Structural validation of the bundled TTL files
report = validate_bundled_ontologies()

# SHACL-based verification of a KG object against mas-shapes(-custom).ttl
verify_kg_object(my_kg_dict)
```

### Query with SPARQL

```sparql
PREFIX mas: <https://outshift-open.github.io/oxp-ontology/mas#>

SELECT ?agent ?task WHERE {
    ?agent a mas:Agent ;
           mas:executes ?task .
}
```

## Documentation

Full ontology documentation (Widoco reference docs and WebVOWL visualizations
for each component), versioning strategy, and the source repository are at:

**https://outshift-open.github.io/observe-and-explain-platform/**

## License

Apache-2.0. The bundled ontology files declare
`dcterms:license <https://opensource.org/licenses/Apache-2.0>` in their headers.
