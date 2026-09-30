#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query builders for the **Labels** domain.

Provides SQL query strings for CRUD operations on the ``trace_labels``
table.  All reads use ``FINAL`` so ClickHouse's ReplacingMergeTree
returns only the latest row per ``session_id``.
"""

from __future__ import annotations

from typing import Optional

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trace_labels
(
    session_id  String,
    label       Bool,
    labeler     String,
    reason      Nullable(String),
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY session_id
"""


def get_label_query(session_id: str) -> str:
    """Return the SELECT query for a single label by *session_id*."""
    return (
        "SELECT session_id, label, labeler, reason, updated_at "
        "FROM trace_labels FINAL "
        f"WHERE session_id = '{session_id}'"
    )


def upsert_label_query(
    session_id: str,
    label: bool,
    labeler: str,
    reason: Optional[str] = None,
) -> str:
    """Return an INSERT query that upserts a label row."""
    label_int = 1 if label else 0
    reason_sql = f"'{reason}'" if reason is not None else "NULL"
    return (
        "INSERT INTO trace_labels (session_id, label, labeler, reason) "
        f"VALUES ('{session_id}', {label_int}, '{labeler}', {reason_sql})"
    )


def delete_label_query(session_id: str) -> str:
    """Return a lightweight DELETE for ClickHouse."""
    return f"DELETE FROM trace_labels WHERE session_id = '{session_id}'"
