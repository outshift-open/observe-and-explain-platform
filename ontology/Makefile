.PHONY: help clean validate docs generate-models generate-shapes

# Default target
help:
	@echo "OXP Ontology Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  validate         - Validate ontology files with Protégé/SPARQL"
	@echo "  docs             - Generate documentation with WIDOCO"
	@echo "  generate-models  - Generate Pydantic KG node/edge models from the ontology"
	@echo "  generate-shapes  - Scaffold mas-shapes.ttl (SHACL) from the ontology"
	@echo "  clean            - Remove generated files"
	@echo "  help             - Show this help message"
	@echo ""
	@echo "Note: Metrics catalog is maintained in MCE repository"

# Generate Pydantic KG node/edge models from the bundled ontology
generate-models:
	@echo "Generating Pydantic KG models from ontology..."
	@python3 scripts/generate_models.py
	@echo "✓ Models generated in src/oxp_ontology/models/"

# Scaffold mas-shapes.ttl (SHACL) from the bundled ontology. Structural shape
# (sh:targetClass, sh:path, sh:datatype/sh:class, sh:node inheritance) comes
# straight from the ontology; sh:minCount/sh:severity are left as TODO
# placeholders for a human to set per property. This OVERWRITES
# src/oxp_ontology/mas-shapes.ttl -- it's gitignored/regenerated (like the
# Pydantic models) and safe to overwrite. Hand-maintained SPARQL/cross-node
# shapes live separately in src/oxp_ontology/mas-shapes-custom.ttl, which
# this target never touches.
generate-shapes:
	@echo "Generating mas-shapes.ttl (SHACL) from ontology..."
	@python3 scripts/generate_shacl_shapes.py
	@echo "✓ Shapes generated in src/oxp_ontology/mas-shapes.ttl"

# Validate ontology files
validate:
	@echo "Validating ontology files..."
	@echo "TODO: Add Protégé CLI validation or SPARQL checks"
	@echo "  - src/oxp_ontology/mas-ontology.ttl"
	@echo "  - src/oxp_ontology/metrics-ontology.ttl"

# Generate documentation with WIDOCO
docs:
	@echo "Generating documentation with WIDOCO..."
	@java -jar widoco.jar -ontFile src/oxp_ontology/mas-ontology.ttl -outFolder docs/mas-ontology -getOntologyMetadata -oops -rewriteAll
	@java -jar widoco.jar -ontFile src/oxp_ontology/metrics-ontology.ttl -outFolder docs/metrics-ontology -getOntologyMetadata -oops -rewriteAll
	@echo "✓ Documentation generated in docs/"

# Clean generated files
clean:
	@echo "Cleaning generated files..."
	@rm -rf docs/mas-ontology docs/metrics-ontology
	@rm -rf src/oxp_ontology/models/nodes src/oxp_ontology/models/edges
	@rm -f src/oxp_ontology/mas-shapes.ttl
	@echo "✓ Cleaned generated documentation, KG models, and SHACL shapes"
