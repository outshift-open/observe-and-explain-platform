#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Convert all CSV files in data/csv/ into ClickHouse SQL files in data/sql/.

Each CSV is expected to have:
  - Row 0: column names (header)
  - Row 1: ClickHouse column types (e.g. String, UInt64, DateTime64(9), …)
  - Row 2+: data rows

The generated SQL contains a CREATE TABLE IF NOT EXISTS statement followed by
INSERT INTO … VALUES statements.

Usage:
    python scripts/csv_to_sql.py
"""

import csv
import os
import sys

# ── Paths ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_DIR = os.path.join(PROJECT_ROOT, "data", "csv")
SQL_DIR = os.path.join(PROJECT_ROOT, "data", "sql")


def _escape_sql(value: str) -> str:
    """Escape single quotes for SQL string literals."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _format_value(value: str, col_type: str) -> str:
    """Format a CSV cell as a ClickHouse SQL literal based on its column type."""
    # Numeric types — emit without quotes
    if col_type in (
        "UInt8",
        "UInt16",
        "UInt32",
        "UInt64",
        "Int8",
        "Int16",
        "Int32",
        "Int64",
        "Float32",
        "Float64",
    ):
        return value if value else "0"

    # Everything else (String, DateTime64, Map, Array, LowCardinality, …)
    return f"'{_escape_sql(value)}'"


def convert_csv_to_sql(csv_path: str, sql_path: str) -> None:
    """Read *csv_path* and write a ClickHouse-compatible SQL file to *sql_path*."""
    table_name = os.path.splitext(os.path.basename(csv_path))[0]  # e.g. "otel_traces"

    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        columns = next(reader)  # Row 0 — header
        col_types = next(reader)  # Row 1 — ClickHouse types
        data_rows = list(reader)  # Row 2+ — data

    # ── BUILD SQL ────────────────────────────────────────────────────────

    lines: list[str] = []

    # Database
    lines.append("CREATE DATABASE IF NOT EXISTS oxp;\n")

    # CREATE TABLE
    lines.append(f"CREATE TABLE IF NOT EXISTS oxp.{table_name}")
    lines.append("(")
    col_defs = []
    for col, ctype in zip(columns, col_types):
        # Quote column names that contain dots (e.g. Events.Timestamp)
        quoted = f"`{col}`" if "." in col else col
        col_defs.append(f"    {quoted} {ctype}")
    lines.append(",\n".join(col_defs))
    lines.append(")")
    lines.append("ENGINE = MergeTree()")
    lines.append("ORDER BY tuple();\n")

    # INSERT statements (one per row to avoid excessively long lines)
    if data_rows:
        col_list = ", ".join(f"`{c}`" if "." in c else c for c in columns)
        for row in data_rows:
            values = ", ".join(
                _format_value(val, ctype) for val, ctype in zip(row, col_types)
            )
            lines.append(
                f"INSERT INTO oxp.{table_name} ({col_list}) VALUES ({values});"
            )

    lines.append("")  # trailing newline

    # ── WRITE ────────────────────────────────────────────────────────────

    os.makedirs(os.path.dirname(sql_path), exist_ok=True)
    with open(sql_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    print(
        f"  {os.path.basename(csv_path)} → {os.path.relpath(sql_path, PROJECT_ROOT)}  ({len(data_rows)} rows)"
    )


def main() -> None:
    if not os.path.isdir(CSV_DIR):
        print(f"CSV directory not found: {CSV_DIR}", file=sys.stderr)
        sys.exit(1)

    csv_files = sorted(f for f in os.listdir(CSV_DIR) if f.endswith(".csv"))
    if not csv_files:
        print("No CSV files found in data/csv/")
        return

    print(f"Converting {len(csv_files)} CSV file(s):\n")
    for filename in csv_files:
        csv_path = os.path.join(CSV_DIR, filename)
        sql_name = os.path.splitext(filename)[0] + ".sql"
        sql_path = os.path.join(SQL_DIR, sql_name)
        convert_csv_to_sql(csv_path, sql_path)

    print("\nDone.")


if __name__ == "__main__":
    main()
