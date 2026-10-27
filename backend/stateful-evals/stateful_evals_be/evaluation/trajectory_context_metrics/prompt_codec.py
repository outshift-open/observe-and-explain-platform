# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0
"""Lossless final-prompt storage; no artifact selection or interpretation.

The original context stays unchanged. A collision-free marker encodes shared
JSON values and homogeneous record arrays; ``unpack(pack(value))`` restores the
JSON value. Column names, absent fields, nulls, attribution and IDs are retained.
"""

from __future__ import annotations

from collections import Counter
import json
from typing import Any


FORMAT = "lossless-record-tables-v1"
FORMAT_INSTRUCTIONS = """\
trajectory_context can use lossless-record-tables-v1 storage. Its root is the
original context. The marker names a reserved key absent from original objects.
An object containing only that key and an integer references records[integer].
An object containing only that key and ["o", schema_index, values] is one object;
["a", schema_index, rows] is an array of objects. schemas[schema_index] gives the
field names; each values row supplies corresponding values in order. Resolve
nested references recursively, including in records.
All other objects and arrays retain their ordinary JSON meaning. source_texts
is unchanged; source_text_ref still addresses its exact text body. This encoding
does not merge events, actors, responsibilities or sources. Judge their original
scope and provenance. Cite only supplied original artifact/source/text IDs,
never storage record numbers, schema numbers or the reserved marker.
"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def pack(value: Any) -> dict[str, Any]:
    """Pack the existing JSON context, preserving all values and evidence IDs."""
    # Match the JSON representation used by the final prompt, including its
    # existing default=str handling of non-JSON scalar objects.
    value = json.loads(_json(value))
    counts: Counter[str] = Counter()
    shapes: Counter[tuple[str, ...]] = Counter()
    keys: set[str] = set()

    def count(item: Any) -> None:
        if isinstance(item, (dict, list, str)):
            signature = _json(item)
            if len(signature) >= 24:
                counts[signature] += 1
                if counts[signature] > 1:
                    return  # Children of a shared value are encoded once.
        if isinstance(item, dict):
            keys.update(item)
            shapes[tuple(item)] += 1
            for child in item.values():
                count(child)
        elif isinstance(item, list):
            for child in item:
                count(child)

    count(value)
    marker = "@context"
    while marker in keys:
        marker += "_"
    records: list[Any] = []
    indexes: dict[str, int] = {}
    schemas: list[list[str]] = []
    schema_indexes: dict[tuple[str, ...], int] = {}

    def encode(item: Any, *, share: bool = True) -> Any:
        if share and isinstance(item, (dict, list, str)):
            signature = _json(item)
            if counts[signature] > 1:
                if signature not in indexes:
                    indexes[signature] = len(records)
                    records.append(None)
                    records[indexes[signature]] = encode(item, share=False)
                return {marker: indexes[signature]}
        if not isinstance(item, (dict, list)):
            return item
        array = isinstance(item, list)
        if array:
            # Prefer one array schema over one object command per row. Shared
            # whole records still take precedence over columnar representation.
            if (len(item) < 2 or not all(isinstance(row, dict) for row in item)
                    or not item[0] or any(tuple(row) != tuple(item[0]) for row in item)
                    or any(counts[_json(row)] > 1 for row in item)):
                return [encode(child) for child in item]
            fields = tuple(item[0])
            rows = [[encode(child) for child in row.values()] for row in item]
            plain = [dict(zip(fields, row)) for row in rows]
        else:
            fields = tuple(item)
            rows = [encode(child) for child in item.values()]
            plain = dict(zip(fields, rows))
            if not fields or shapes[fields] < 2:
                return plain
        index = schema_indexes.get(fields, len(schemas))
        table = {marker: ["a" if array else "o", index, rows]}
        schema_cost = len(_json(fields)) if fields not in schema_indexes else 0
        if len(_json(table)) + schema_cost / (1 if array else shapes[fields]) >= len(_json(plain)):
            return plain
        if fields not in schema_indexes:
            schema_indexes[fields] = index
            schemas.append(list(fields))
        return table

    root = encode(value)
    return {"format": FORMAT, "marker": marker, "schemas": schemas,
            "records": records, "root": root}


def unpack(value: dict[str, Any]) -> Any:
    """Expand a packed context for audits without consulting a sidecar."""
    if value.get("format") != FORMAT:
        raise ValueError("Unknown context encoding")
    marker, records, schemas = value["marker"], value["records"], value["schemas"]
    if not isinstance(marker, str) or not isinstance(records, list) or not isinstance(schemas, list):
        raise ValueError("Invalid context encoding tables")
    cache: dict[int, Any] = {}
    active: set[int] = set()

    def index(value: Any, size: int) -> int:
        if type(value) is not int or not 0 <= value < size:
            raise ValueError("Invalid context table index")
        return value

    def decode(item: Any) -> Any:
        if isinstance(item, dict) and set(item) == {marker}:
            command = item[marker]
            if type(command) is int:
                number = index(command, len(records))
                if number in active:
                    raise ValueError("Cyclic context reference")
                if number not in cache:
                    active.add(number)
                    cache[number] = decode(records[number])
                    active.remove(number)
                return cache[number]
            if (not isinstance(command, list) or len(command) != 3
                    or command[0] not in ("o", "a")):
                raise ValueError("Invalid context storage command")
            fields = schemas[index(command[1], len(schemas))]
            rows = [command[2]] if command[0] == "o" else command[2]
            if (not isinstance(fields, list) or not all(isinstance(key, str) for key in fields)
                    or len(set(fields)) != len(fields) or not isinstance(rows, list)):
                raise ValueError("Invalid context record schema")
            if any(not isinstance(row, list) or len(row) != len(fields) for row in rows):
                raise ValueError("Invalid context record row")
            decoded = [{key: decode(child) for key, child in zip(fields, row)} for row in rows]
            return decoded[0] if command[0] == "o" else decoded
        if isinstance(item, dict):
            return {key: decode(child) for key, child in item.items()}
        if isinstance(item, list):
            return [decode(child) for child in item]
        return item

    return decode(value["root"])
