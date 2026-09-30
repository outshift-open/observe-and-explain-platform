#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Generate a single WebVOWL-compatible JSON graph merging multiple ontology
TTL files into one visualization (unlike generate_webvowl_json_generic.py,
which renders exactly one ontology's own namespace per call).

Usage: python generate_webvowl_json_merged.py <output.json> <name> <iri> <input1.ttl> [input2.ttl ...]
"""

import json
import os
import sys

from rdflib import BNode, OWL, RDF, RDFS, Graph, Namespace

if len(sys.argv) < 5:
    print(
        "Usage: generate_webvowl_json_merged.py <output.json> <name> <iri> "
        "<input1.ttl> [input2.ttl ...]"
    )
    sys.exit(1)

output_file = sys.argv[1]
ontology_name = sys.argv[2]
ontology_iri = sys.argv[3]
input_files = sys.argv[4:]

DCTERMS = Namespace("http://purl.org/dc/terms/")

g = Graph()
for path in input_files:
    g.parse(path, format="turtle")


def get_name(uri):
    """Extract the local name from a URI."""
    return str(uri).split("#")[-1].split("/")[-1]


def get_comment(uri):
    """Get the rdfs:comment for a URI, if any."""
    return str(next(g.objects(uri, RDFS.comment), ""))


# Collect every class across every merged file/namespace (no per-file filter).
classes = []
class_ids = {}
node_id = 0

for cls in g.subjects(RDF.type, OWL.Class):
    cls_name = get_name(cls)
    if cls_name in class_ids:
        continue  # same class re-declared/extended across files (e.g. mas:Metric)

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

# Collect every object property, resolving domain/range across the merged graph
# (this is what makes cross-file edges work: e.g. metrics:ofMetricType's range
# mas:Metric resolves correctly because mas:Metric's class node already exists).
properties = []
prop_id = node_id
union_node_ids = {}  # frozenset of member class ids -> synthetic owl:unionOf node id


def resolve_endpoint(node):
    """Return the WebVOWL node id for a domain/range value, creating a synthetic
    owl:unionOf node (per WebVOWL's real schema: a class entry with a "union"
    array of member ids, which the viewer auto-expands into fan-out edges) when
    the value is a blank-node owl:unionOf. Returns None if unresolvable."""
    if not node:
        return None
    if not isinstance(node, BNode):
        name = get_name(node)
        return class_ids.get(name)

    union_list = next(g.objects(node, OWL.unionOf), None)
    if not union_list:
        return None
    member_ids = []
    for item in g.items(union_list):
        member_name = get_name(item)
        if member_name in class_ids:
            member_ids.append(class_ids[member_name])
    if len(member_ids) < 2:
        return member_ids[0] if member_ids else None

    key = frozenset(member_ids)
    if key in union_node_ids:
        return union_node_ids[key]

    union_id = str(node_id_counter())
    classes.append(
        {
            "id": union_id,
            "type": "owl:unionOf",
            "union": [str(m) for m in member_ids],
        }
    )
    union_node_ids[key] = union_id
    return union_id


def node_id_counter():
    global prop_id
    value = prop_id
    prop_id += 1
    return value


for prop in g.subjects(RDF.type, OWL.ObjectProperty):
    prop_name = get_name(prop)
    comment = get_comment(prop)

    domain = next(g.objects(prop, RDFS.domain), None)
    range_val = next(g.objects(prop, RDFS.range), None)

    domain_id = resolve_endpoint(domain)
    range_id = resolve_endpoint(range_val)

    if domain_id is None or range_id is None:
        continue

    edge = {
        "id": str(node_id_counter()),
        "type": "owl:ObjectProperty",
        "iri": str(prop),
        "label": prop_name,
        "domain": str(domain_id),
        "range": str(range_id),
    }
    if comment:
        edge["comment"] = comment

    properties.append(edge)

# WebVOWL keeps datatype-property ranges (xsd:string etc.) in a SEPARATE
# top-level "datatype" array, distinct from "class" -- one rdfs:Datatype node
# per distinct XSD type actually used, created lazily as encountered.
datatypes = []
datatype_ids = {}


def resolve_datatype(range_val):
    if range_val is None or isinstance(range_val, BNode):
        return None
    iri = str(range_val)
    if iri in datatype_ids:
        return datatype_ids[iri]
    dtype_id = str(node_id_counter())
    datatypes.append(
        {
            "id": dtype_id,
            "type": "rdfs:Datatype",
            "iri": iri,
            "label": get_name(range_val),
        }
    )
    datatype_ids[iri] = dtype_id
    return dtype_id


for prop in g.subjects(RDF.type, OWL.DatatypeProperty):
    prop_name = get_name(prop)
    comment = get_comment(prop)

    domain = next(g.objects(prop, RDFS.domain), None)
    range_val = next(g.objects(prop, RDFS.range), None)

    domain_id = resolve_endpoint(domain)
    range_id = resolve_datatype(range_val)

    if domain_id is None or range_id is None:
        continue

    edge = {
        "id": str(node_id_counter()),
        "type": "owl:DatatypeProperty",
        "iri": str(prop),
        "label": prop_name,
        "domain": str(domain_id),
        "range": str(range_id),
    }
    if comment:
        edge["comment"] = comment

    properties.append(edge)

# Collect subclass relationships between two known classes (direct rdfs:subClassOf
# only -- skip blank-node targets, e.g. owl:Restriction-based subClassOf, which
# aren't a class-to-class edge WebVOWL can draw).
for child in g.subjects(RDF.type, OWL.Class):
    child_name = get_name(child)
    if child_name not in class_ids:
        continue
    for parent in g.objects(child, RDFS.subClassOf):
        if isinstance(parent, BNode):
            continue
        parent_name = get_name(parent)
        if parent_name not in class_ids or parent_name == child_name:
            continue
        edge = {
            "id": str(node_id_counter()),
            "type": "rdfs:subClassOf",
            "iri": str(RDFS.subClassOf),
            "label": "subClassOf",
            "domain": str(class_ids[child_name]),
            "range": str(class_ids[parent_name]),
        }
        properties.append(edge)

webvowl_data = {
    "header": {
        "title": ontology_name,
        "description": f"Merged view of: {', '.join(os.path.basename(p) for p in input_files)}",
        "iri": ontology_iri,
        "languages": ["en"],
        "version": "",
    },
    "namespace": [],
    "class": classes,
    "datatype": datatypes,
    "property": properties,
    "classAttribute": [],
    "datatypeAttribute": [],
    "propertyAttribute": [],
}

os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
with open(output_file, "w") as f:
    json.dump(webvowl_data, f, indent=2)

print(f"✅ Merged WebVOWL JSON generated: {output_file}")
print(f"   Files merged: {len(input_files)}")
print(f"   Classes: {len(classes)}")
print(f"   Datatypes: {len(datatypes)}")
print(f"   Properties: {len(properties)}")
