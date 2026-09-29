# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Generate LODE-style HTML documentation from OWL ontology.
Lightweight alternative to online LODE service.
"""

from datetime import datetime

from rdflib import OWL, RDF, RDFS, Graph


def generate_lode_html(ttl_file, output_file):
    """Generate simple HTML documentation similar to LODE."""

    g = Graph()
    g.parse(ttl_file, format="turtle")

    # Extract ontology metadata
    ontology_iri = None
    for s in g.subjects(RDF.type, OWL.Ontology):
        ontology_iri = str(s)
        break

    # Get classes and properties
    classes = sorted(set(g.subjects(RDF.type, OWL.Class)))
    properties = sorted(
        set(g.subjects(RDF.type, OWL.ObjectProperty))
        | set(g.subjects(RDF.type, OWL.DatatypeProperty))
    )

    # Generate HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Agent System Ontology - LODE Documentation</title>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            line-height: 1.6;
            max-width: 900px;
            margin: 40px auto;
            padding: 20px;
            background: #f9f9f9;
        }}
        h1 {{ color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px; }}
        h2 {{ color: #333; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px; }}
        h3 {{ color: #555; margin-top: 20px; }}
        .entity {{
            background: white;
            border-left: 4px solid #1a73e8;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .entity-name {{
            font-size: 18px;
            font-weight: bold;
            color: #1a73e8;
            margin-bottom: 8px;
        }}
        .entity-uri {{
            font-family: monospace;
            font-size: 12px;
            color: #666;
            background: #f5f5f5;
            padding: 4px 8px;
            border-radius: 3px;
            display: inline-block;
            margin-bottom: 8px;
        }}
        .description {{
            color: #444;
            margin: 10px 0;
        }}
        .back-link {{
            display: inline-block;
            margin: 20px 0;
            padding: 8px 16px;
            background: #1a73e8;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }}
        .back-link:hover {{ background: #1557b0; }}
        .metadata {{
            background: #e8f0fe;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }}
    </style>
</head>
<body>
    <a href="../" class="back-link">← Back to Documentation Index</a>
    
    <h1>Multi-Agent System Ontology</h1>
    
    <div class="metadata">
        <p><strong>Ontology IRI:</strong> <code>{ontology_iri or "N/A"}</code></p>
        <p><strong>Generated:</strong> {datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")}</p>
        <p><strong>Format:</strong> LODE-style lightweight documentation</p>
    </div>
    
    <h2>Table of Contents</h2>
    <ul>
        <li><a href="#classes">Classes ({len(classes)})</a></li>
        <li><a href="#properties">Properties ({len(properties)})</a></li>
    </ul>
    
    <h2 id="classes">Classes</h2>
"""

    # Add classes
    for cls in classes:
        label = g.value(cls, RDFS.label) or cls.split("#")[-1].split("/")[-1]
        comment = g.value(cls, RDFS.comment) or "No description available."

        html += f"""
    <div class="entity">
        <div class="entity-name">{label}</div>
        <div class="entity-uri">{cls}</div>
        <div class="description">{comment}</div>
    </div>
"""

    html += """
    <h2 id="properties">Properties</h2>
"""

    # Add properties
    for prop in properties:
        label = g.value(prop, RDFS.label) or prop.split("#")[-1].split("/")[-1]
        comment = g.value(prop, RDFS.comment) or "No description available."
        domain = g.value(prop, RDFS.domain)
        range_val = g.value(prop, RDFS.range)

        extra_info = ""
        if domain:
            domain_label = (
                g.value(domain, RDFS.label) or domain.split("#")[-1].split("/")[-1]
            )
            extra_info += f"<br><strong>Domain:</strong> {domain_label}"
        if range_val:
            range_label = (
                g.value(range_val, RDFS.label)
                or range_val.split("#")[-1].split("/")[-1]
            )
            extra_info += f"<br><strong>Range:</strong> {range_label}"

        html += f"""
    <div class="entity">
        <div class="entity-name">{label}</div>
        <div class="entity-uri">{prop}</div>
        <div class="description">{comment}{extra_info}</div>
    </div>
"""

    html += """
    <a href="../" class="back-link">← Back to Documentation Index</a>
</body>
</html>
"""

    with open(output_file, "w") as f:
        f.write(html)

    print(f"✅ LODE-style HTML generated: {output_file}")
    print(f"   Classes: {len(classes)}")
    print(f"   Properties: {len(properties)}")


if __name__ == "__main__":
    import sys

    generate_lode_html(
        sys.argv[1] if len(sys.argv) > 1 else "src/oxp_ontology/mas-ontology.ttl",
        sys.argv[2] if len(sys.argv) > 2 else "docs/lode/index.html",
    )
