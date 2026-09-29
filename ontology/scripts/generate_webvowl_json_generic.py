#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Generate WebVOWL-compatible JSON for any ontology
Usage: python generate_webvowl_json_generic.py <input.ttl> <output.json> <ontology-name> <ontology-iri>
"""

import json
import os
import sys

from rdflib import OWL, RDF, RDFS, Graph, Namespace

if len(sys.argv) < 5:
    print(
        "Usage: generate_webvowl_json_generic.py <input.ttl> <output.json> <name> <iri>"
    )
    sys.exit(1)

input_file = sys.argv[1]
output_file = sys.argv[2]
ontology_name = sys.argv[3]
ontology_iri = sys.argv[4]

# Load ontology
g = Graph()
g.parse(input_file, format="turtle")

# Namespaces
DCTERMS = Namespace("http://purl.org/dc/terms/")


def get_name(uri):
    """Extract name from URI"""
    return str(uri).split("#")[-1].split("/")[-1]


def get_comment(uri):
    """Get comment/description"""
    return str(next(g.objects(uri, RDFS.comment), ""))


# Detect namespace from file
detected_ns = None
for cls in g.subjects(RDF.type, OWL.Class):
    uri_str = str(cls)
    if "#" in uri_str:
        detected_ns = Namespace(uri_str.rsplit("#", 1)[0] + "#")
        break

# Collect classes
classes = []
class_ids = {}
node_id = 0

for cls in g.subjects(RDF.type, OWL.Class):
    # Only include classes from this ontology's namespace
    if detected_ns and not str(cls).startswith(str(detected_ns)):
        continue

    cls_name = get_name(cls)
    comment = get_comment(cls)

    class_ids[cls_name] = node_id

    node = {
        "id": str(node_id),
        "type": "owl:Class",
        "iri": str(cls),
        "label": cls_name,
    }

    if comment:
        node["comment"] = comment

    classes.append(node)
    node_id += 1

# Collect properties (relationships)
properties = []
prop_id = node_id

for prop in g.subjects(RDF.type, OWL.ObjectProperty):
    # Only include properties from this ontology's namespace
    if detected_ns and not str(prop).startswith(str(detected_ns)):
        continue

    prop_name = get_name(prop)
    comment = get_comment(prop)

    domain = next(g.objects(prop, RDFS.domain), None)
    range_val = next(g.objects(prop, RDFS.range), None)

    if domain and range_val:
        # Handle simple domain/range (not unionOf for now)
        if not str(domain).startswith("_:") and not str(range_val).startswith("_:"):
            domain_name = get_name(domain)
            range_name = get_name(range_val)

            if domain_name in class_ids and range_name in class_ids:
                edge = {
                    "id": str(prop_id),
                    "type": "owl:objectProperty",
                    "iri": str(prop),
                    "label": prop_name,
                    "domain": str(class_ids[domain_name]),
                    "range": str(class_ids[range_name]),
                }

                if comment:
                    edge["comment"] = comment

                properties.append(edge)
                prop_id += 1
        else:
            # Handle unionOf - create multiple edges
            domains = []
            ranges = []

            if str(domain).startswith("_:"):
                union_members = list(g.objects(domain, OWL.unionOf))
                if union_members:
                    for item in g.items(union_members[0]):
                        domains.append(get_name(item))
            else:
                domains.append(get_name(domain))

            if str(range_val).startswith("_:"):
                union_members = list(g.objects(range_val, OWL.unionOf))
                if union_members:
                    for item in g.items(union_members[0]):
                        ranges.append(get_name(item))
            else:
                ranges.append(get_name(range_val))

            # Create edge for each combination
            for domain_name in domains:
                for range_name in ranges:
                    if domain_name in class_ids and range_name in class_ids:
                        edge = {
                            "id": str(prop_id),
                            "type": "owl:objectProperty",
                            "iri": str(prop),
                            "label": prop_name,
                            "domain": str(class_ids[domain_name]),
                            "range": str(class_ids[range_name]),
                        }

                        if comment:
                            edge["comment"] = comment

                        properties.append(edge)
                        prop_id += 1

# Get ontology metadata
title = str(next(g.objects(None, DCTERMS.title), ontology_name))
description = str(next(g.objects(None, DCTERMS.description), ""))
version = str(next(g.objects(None, DCTERMS.modified), ""))

# Create WebVOWL JSON structure
webvowl_data = {
    "header": {
        "title": title,
        "description": description,
        "iri": ontology_iri,
        "languages": ["en"],
        "version": version,
    },
    "namespace": [],
    "class": classes,
    "property": properties,
    "classAttribute": [],
    "propertyAttribute": [],
}

# Write to file
os.makedirs(os.path.dirname(output_file), exist_ok=True)
with open(output_file, "w") as f:
    json.dump(webvowl_data, f, indent=2)

print(f"✅ WebVOWL JSON generated: {output_file}")
print(f"   Ontology: {ontology_name}")
print(f"   Classes: {len(classes)}")
print(f"   Properties: {len(properties)}")
