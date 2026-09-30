#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Surgically inject SHACL PropertyShape dual-typing + placeholder
sh:minCount/sh:severity into every owl:DatatypeProperty/owl:ObjectProperty
declaration in a TTL file, preserving all existing text (comments, ordering,
formatting) exactly. Skips properties with no rdfs:domain (nothing to target).

This is a line-based state machine, not a full Turtle re-serialization,
specifically so it does not disturb anything else in the file.

Naturally idempotent: it matches only the bare `rdf:type owl:DatatypeProperty ;`
/ `owl:ObjectProperty ;` form, so a property that's already been dual-typed
(`rdf:type owl:DatatypeProperty, sh:PropertyShape ;`) is left untouched on a
second run -- safe to run again after adding new properties to an ontology
file; it will only inject the new ones.

Usage: python scripts/inject_shacl_into_properties.py <file1.ttl> [file2.ttl ...]
Requires the file to already declare `@prefix sh: <http://www.w3.org/ns/shacl#> .`
"""

import re
import sys

PROP_START_RE = re.compile(
    r"^(\S+) rdf:type (owl:DatatypeProperty|owl:ObjectProperty) ;\s*$"
)


def find_block_end(lines, start_idx):
    """Return the index of the line that ends this property's statement
    (a bare trailing '.' outside any quote/bracket/paren nesting)."""
    paren_depth = 0
    bracket_depth = 0
    in_triple_quote = False
    i = start_idx
    while i < len(lines):
        line = lines[i]
        # crude but sufficient scanner for this file's style: no nested
        # triple-quotes-within-triple-quotes, no unbalanced brackets inside
        # single-line string literals containing '[' ']' etc. handled by
        # only counting brackets when not inside a triple-quoted string.
        if in_triple_quote:
            if '"""' in line:
                in_triple_quote = False
            i += 1
            continue
        # count triple-quote toggles
        tq_count = line.count('"""')
        if tq_count % 2 == 1:
            in_triple_quote = not in_triple_quote
        if not in_triple_quote:
            # strip single-line double-quoted string contents so brackets inside
            # comments (e.g. "{'lower': .., 'upper': ..}") don't get counted.
            stripped_line = re.sub(r'"(?:[^"\\]|\\.)*"', '""', line)
            paren_depth += stripped_line.count("(") - stripped_line.count(")")
            bracket_depth += stripped_line.count("[") - stripped_line.count("]")
            rstripped = stripped_line.rstrip()
            if rstripped.endswith(".") and paren_depth == 0 and bracket_depth == 0:
                return i
        i += 1
    raise ValueError(f"Could not find end of block starting at line {start_idx + 1}")


def extract_domain_classes(block_text):
    """Pull the class name(s) out of an rdfs:domain clause within this block."""
    m = re.search(r"rdfs:domain\s+(.+?)\s*;", block_text, re.DOTALL)
    if not m:
        return []
    domain_text = m.group(1).strip()
    if domain_text.startswith("["):
        # [ owl:unionOf (:A :B mas:C) ] or [ rdf:type owl:Class ; owl:unionOf ( ... ) ]
        union_m = re.search(r"owl:unionOf\s*\(([^)]*)\)", domain_text)
        if union_m:
            return union_m.group(1).split()
        return []
    return [domain_text]


def process_file(path):
    with open(path) as f:
        lines = f.readlines()

    out = []
    i = 0
    injected_count = 0
    skipped_no_domain = []

    while i < len(lines):
        m = PROP_START_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue

        prop_name, prop_type = m.group(1), m.group(2)
        end_idx = find_block_end(lines, i)
        block_lines = lines[i : end_idx + 1]
        block_text = "".join(block_lines)

        domains = extract_domain_classes(block_text)
        if not domains:
            skipped_no_domain.append(prop_name)
            out.extend(block_lines)
            i = end_idx + 1
            continue

        # Determine indentation from the second line of the block (the first
        # predicate after rdf:type), so injected lines match.
        indent = "    "
        for block_line in block_lines[1:]:
            if block_line.strip():
                indent = block_line[: len(block_line) - len(block_line.lstrip())]
                break

        target_class_list = ", ".join(domains)
        new_first_line = lines[i].replace(
            f"rdf:type {prop_type} ;", f"rdf:type {prop_type}, sh:PropertyShape ;"
        )
        out.append(new_first_line)
        out.append(f"{indent}sh:path {prop_name} ;\n")
        out.append(f"{indent}sh:targetClass {target_class_list} ;\n")
        out.append(f"{indent}sh:minCount 1 ;\n")
        out.append(
            f"{indent}sh:severity sh:Info ;  # TODO: sh:Violation (mandatory) | sh:Warning (recommended)\n"
        )
        out.extend(block_lines[1:])
        injected_count += 1
        i = end_idx + 1

    with open(path, "w") as f:
        f.writelines(out)

    print(
        f"{path}: injected {injected_count} properties, skipped {len(skipped_no_domain)} with no domain"
    )
    if skipped_no_domain:
        print(f"  skipped (no rdfs:domain): {', '.join(skipped_no_domain)}")


if __name__ == "__main__":
    for path in sys.argv[1:]:
        process_file(path)
