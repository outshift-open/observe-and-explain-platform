#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Seed the otel_traces table with sample data."""

import os
import sys


def seed_database_test(csv_path: str | None = None) -> None:
    """Create the otel_traces table and populate it from CSV.

    Delegates to the active :class:`OtelRepository` implementation so
    the same call works for both SQLite and ClickHouse backends.
    """
    from oxp.repositories import get_otel_repository

    repo = get_otel_repository()

    # Verify the database connection is usable before proceeding.
    try:
        repo.check_connection()
    except Exception as exc:
        print(f"ERROR: Cannot connect to the oxp database: {exc}", file=sys.stderr)
        sys.exit(1)

    if csv_path is None:
        csv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data",
            "csv",
            "otel_traces.csv",
        )

    print(f">>> SQLite database seed file: {csv_path}")
    repo.seed(csv_path)
