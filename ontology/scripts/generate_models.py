# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

import os
import re
import textwrap

from rdflib import OWL, RDF, RDFS, XSD, Graph
from rdflib.namespace import SH

# Map XSD types to Python type hints
XSD_TYPE_MAP = {
    XSD.string: "str",
    XSD.integer: "int",
    XSD.float: "float",
    XSD.double: "float",
    XSD.decimal: "float",
    XSD.boolean: "bool",
    XSD.dateTime: "datetime",
    XSD.date: "date",
}

TYPE_SAFE_DEFAULTS = {
    "str": '""',
    "int": "0",
    "float": "0.0",
    "bool": "False",
    "list": "[]",
    "dict": "{}",
}


def get_python_type(range_node, default="str"):
    """Map an ontology range node to the generated Python type name."""
    if not range_node:
        return default
    return XSD_TYPE_MAP.get(range_node, "str")


def get_fragment(node):
    """Return the URI fragment for RDF URI nodes and ``None`` otherwise."""
    return getattr(node, "fragment", None)


def to_snake_case(name):
    """Convert ontology class or property names to snake_case module names."""
    first_pass = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first_pass).lower()


def resolve_class_names(g, node):
    """Resolve direct, union, or intersection OWL class expressions to names."""
    if node == OWL.Thing:
        return {"Thing"}

    fragment = get_fragment(node)
    if fragment:
        return {fragment}

    union_node = g.value(node, OWL.unionOf)
    if union_node:
        return {
            name
            for item in g.items(union_node)
            for name in resolve_class_names(g, item)
        }

    intersection_node = g.value(node, OWL.intersectionOf)
    if intersection_node:
        return {
            name
            for item in g.items(intersection_node)
            for name in resolve_class_names(g, item)
        }

    return set()


def get_property_domains(g, prop):
    """Return all ontology class names in a property's domain expression."""
    return {
        name
        for domain in g.objects(prop, RDFS.domain)
        for name in resolve_class_names(g, domain)
    }


def get_property_ranges(g, prop):
    """Return all ontology class names in a property's range expression."""
    return {
        name
        for range_node in g.objects(prop, RDFS.range)
        for name in resolve_class_names(g, range_node)
    }


def applies_to_class(domain_names, class_name):
    """Return whether a property domain applies to a generated class name."""
    return "Thing" in domain_names or class_name in domain_names


def format_comment_lines(text, indent="    "):
    """Wrap an rdfs:comment as '# '-prefixed Python comment lines at the
    given indent, respecting ruff's line-length limit (88)."""
    width = 88 - len(indent) - len("# ")
    wrapped = textwrap.wrap(str(text), width=width) or [""]
    return "".join(f"{indent}# {line}\n" for line in wrapped)


def add_field(fields, name, field_type, required, default, description):
    """Add a generated model field if it has not already been inherited locally."""
    if name not in fields:
        fields[name] = (field_type, required, default, description)


def is_required(g, prop):
    """A property is pydantic-required only at sh:minCount >= 1 with
    sh:severity sh:Violation -- the "mandatory" tier of the
    mandatory/recommended/optional convention used throughout the ontology.
    A "recommended" property (minCount 1, severity sh:Warning) still stays
    Optional here: missing it should warn (verify_kg_object), not block
    object construction outright."""
    severity = g.value(prop, SH.severity)
    min_count = g.value(prop, SH.minCount)
    if severity != SH.Violation or min_count is None:
        return False
    try:
        return int(min_count) >= 1
    except (TypeError, ValueError):
        return False


def generate_robust_pydantic_models(ttl_path, output_dir=None):
    """Generate ontology-backed KG node and edge Pydantic models from Turtle."""
    if output_dir is None:
        package_root = os.path.dirname(os.path.dirname(__file__))
        output_dir = os.path.join(package_root, "src", "oxp_ontology", "models")

    g = Graph()
    ttl_paths = ttl_path if isinstance(ttl_path, (list, tuple, set)) else [ttl_path]
    for path in ttl_paths:
        g.parse(path, format="turtle")

    nodes_dir = os.path.join(output_dir, "nodes")
    edges_dir = os.path.join(output_dir, "edges")
    os.makedirs(nodes_dir, exist_ok=True)
    os.makedirs(edges_dir, exist_ok=True)

    # Track defined class names for inheritance resolution
    defined_classes = {
        fragment
        for cls in g.subjects(RDF.type, OWL.Class)
        if (fragment := get_fragment(cls))
    }
    datatype_properties = list(g.subjects(RDF.type, OWL.DatatypeProperty))
    object_properties = list(g.subjects(RDF.type, OWL.ObjectProperty))

    node_exports = []  # (module_name, class_name), for the generated nodes/__init__.py
    edge_exports = []  # (module_name, class_name), for the generated edges/__init__.py

    # 1. Generate Node Classes (owl:Class)
    for cls in g.subjects(RDF.type, OWL.Class):
        if not get_fragment(cls):
            continue
        name = get_fragment(cls)
        module_name = to_snake_case(name)
        node_exports.append((module_name, name))
        filepath = os.path.join(nodes_dir, f"{module_name}.py")

        # Resolve inheritance (rdfs:subClassOf)
        parent_class = "BaseModel"
        for _, _, parent in g.triples((cls, RDFS.subClassOf, None)):
            parent_fragment = get_fragment(parent)
            if (
                parent_fragment
                and parent_fragment in defined_classes
                and parent_fragment != name
            ):
                parent_class = parent_fragment
                break

        class_comment = g.value(cls, RDFS.comment)

        constants = {}
        for predicate, value in g.predicate_objects(cls):
            field_name = get_fragment(predicate)
            if predicate in {RDF.type, RDFS.subClassOf, RDFS.comment} or not field_name:
                continue
            if hasattr(value, "toPython") and field_name not in constants:
                constants[field_name] = repr(str(value.toPython()))

        fields = {}
        for prop in datatype_properties:
            prop_fragment = get_fragment(prop)
            domain_names = get_property_domains(g, prop)
            if prop_fragment and applies_to_class(domain_names, name):
                range_node = g.value(prop, RDFS.range)
                py_type = get_python_type(range_node)
                prop_comment = g.value(prop, RDFS.comment)
                description = (
                    str(prop_comment)
                    if prop_comment
                    else "Datatype property from ontology"
                )
                add_field(
                    fields,
                    prop_fragment,
                    py_type,
                    is_required(g, prop),
                    TYPE_SAFE_DEFAULTS.get(py_type, "None"),
                    description,
                )

        # Build file content
        needs_optional_type = any(
            not req and default == "None" for _, req, default, _ in fields.values()
        )
        used_types = {ftype for ftype, _, _, _ in fields.values()}
        temporal_imports = sorted(used_types & {"datetime", "date"})

        typing_imports = set()
        if constants:
            typing_imports.add("ClassVar")
        if needs_optional_type:
            typing_imports.add("Optional")

        imports = ""
        if fields:
            imports += "from pydantic import Field\n"
        if typing_imports:
            imports += f"from typing import {', '.join(sorted(typing_imports))}\n"
        if temporal_imports:
            imports += f"from datetime import {', '.join(temporal_imports)}\n"
        if parent_class == "BaseModel":
            imports += "from ..base import KGNode\n"
            parent_class = "KGNode"
        else:
            # Assuming nodes are in the same directory
            imports += f"from .{to_snake_case(parent_class)} import {parent_class}\n"

        code = f"{imports}\n\nclass {name}({parent_class}):\n"
        if class_comment:
            code += format_comment_lines(class_comment)
        if not constants and not fields:
            code += "    pass\n"
        else:
            for cname, cvalue in constants.items():
                code += f"    {cname}: ClassVar[str] = {cvalue}\n"
            for fname, (ftype, required, default, description) in fields.items():
                if required:
                    code += (
                        f"    {fname}: {ftype} = Field("
                        f"..., description={description!r})\n"
                    )
                elif default == "None":
                    code += (
                        f"    {fname}: Optional[{ftype}] = Field("
                        f"default=None, description={description!r})\n"
                    )
                else:
                    code += (
                        f"    {fname}: {ftype} = Field("
                        f"default={default}, description={description!r})\n"
                    )

        with open(filepath, "w") as f:
            f.write(code)

    # 2. Generate Edge Classes (owl:ObjectProperty)
    for prop in object_properties:
        if not get_fragment(prop):
            continue
        name = get_fragment(prop)
        module_name = to_snake_case(name)
        edge_exports.append((module_name, name))
        filepath = os.path.join(edges_dir, f"{module_name}.py")

        # Resolve source and target restrictions if specified via domain/range
        source_cls = g.value(prop, RDFS.domain)
        target_cls = g.value(prop, RDFS.range)

        source_types = sorted(resolve_class_names(g, source_cls))
        target_types = sorted(resolve_class_names(g, target_cls))
        source_description = "Source entity instance or ID"
        target_description = "Target entity instance or ID"
        if source_types:
            source_description += f" ({', '.join(source_types)})"
        if target_types:
            target_description += f" ({', '.join(target_types)})"

        code = "from pydantic import Field\nfrom ..base import KGEdge\n\n"
        code += f"class {name}(KGEdge):\n"
        code += f"    source_id: str = Field(..., description={source_description!r})\n"
        code += f"    target_id: str = Field(..., description={target_description!r})\n"

        with open(filepath, "w") as f:
            f.write(code)

    # 3. Re-export every generated class from its package's __init__.py, so
    # callers can write `from oxp_ontology.models.nodes import AgentCall`
    # instead of `from oxp_ontology.models.nodes.agent_call import AgentCall`.
    write_package_init(nodes_dir, node_exports)
    write_package_init(edges_dir, edge_exports)

    return output_dir


def write_package_init(package_dir, exports):
    """Write an ``__init__.py`` re-exporting every (module, class) pair."""
    exports = sorted(exports, key=lambda pair: pair[1])
    lines = [f"from .{module} import {cls}" for module, cls in exports]
    lines.append("")
    lines.append("__all__ = [")
    lines.extend(f"    {cls!r}," for _, cls in exports)
    lines.append("]")
    filepath = os.path.join(package_dir, "__init__.py")
    with open(filepath, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    import oxp_ontology

    ontology_names = sorted(
        getattr(oxp_ontology, "ONTOLOGY_FILES", {"mas": "mas-ontology.ttl"})
    )
    ttl_paths = [oxp_ontology.get_ontology_path(name) for name in ontology_names]
    print(f"Using ontologies from: {', '.join(str(path) for path in ttl_paths)}")
    output_dir = generate_robust_pydantic_models(ttl_paths)
    print(f"Models generated successfully in {output_dir}/")
