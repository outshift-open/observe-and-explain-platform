#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Generate WebVOWL-compatible JSON from MAS Ontology
WebVOWL format: https://github.com/VisualDataWeb/WebVOWL/wiki/JSON-format
"""

import json
import os
import sys

from rdflib import OWL, RDF, RDFS, Graph, Namespace

# Load ontology
g = Graph()
g.parse(
    sys.argv[1] if len(sys.argv) > 1 else "src/oxp_ontology/mas-ontology.ttl",
    format="turtle",
)

# Namespaces
MAS = Namespace("https://outshift-open.github.io/oxp-ontology/mas#")
DCTERMS = Namespace("http://purl.org/dc/terms/")


def get_name(uri):
    """Extract name from URI"""
    return str(uri).split("#")[-1].split("/")[-1]


def get_comment(uri):
    """Get comment/description"""
    return str(next(g.objects(uri, RDFS.comment), ""))


# Collect classes
classes = []
class_ids = {}
node_id = 0

for cls in g.subjects(RDF.type, OWL.Class):
    if str(cls).startswith(str(MAS)):
        cls_name = get_name(cls)
        comment = get_comment(cls)

        # Get additional metadata
        block = next(g.objects(cls, MAS.block), None)
        span_level = next(g.objects(cls, MAS.spanLevel), None)

        class_ids[cls_name] = node_id

        node = {
            "id": str(node_id),
            "type": "owl:Class",
            "iri": str(cls),
            "label": cls_name,
        }

        if comment:
            node["comment"] = comment

        # Add attributes for filtering/coloring
        attributes = []
        if block:
            attributes.append(f"block:{get_name(block)}")
        if span_level:
            attributes.append(f"level:{span_level}")

        if attributes:
            node["attributes"] = attributes

        classes.append(node)
        node_id += 1

# Collect properties (relationships)
properties = []
prop_id = node_id

for prop in g.subjects(RDF.type, OWL.ObjectProperty):
    if str(prop).startswith(str(MAS)):
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
title = str(next(g.objects(None, DCTERMS.title), "MAS Ontology"))
description = str(next(g.objects(None, DCTERMS.description), ""))

# Create WebVOWL JSON structure
webvowl_data = {
    "header": {
        "title": title,
        "description": description,
        "iri": "https://outshift-open.github.io/oxp-ontology/mas",
        "languages": ["en"],
        "version": str(next(g.objects(None, DCTERMS.modified), "")),
    },
    "namespace": [],
    "class": classes,
    "property": properties,
    "classAttribute": [],
    "propertyAttribute": [],
}

# Write to file
output_path = (
    sys.argv[2] if len(sys.argv) > 2 else "docs/webvowl/data/mas-ontology.json"
)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w") as f:
    json.dump(webvowl_data, f, indent=2)

print(f"✅ WebVOWL JSON generated: {output_path}")
print(f"   Classes: {len(classes)}")
print(f"   Properties: {len(properties)}")
