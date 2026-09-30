#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Labels-domain methods for :class:`LocalClient`.

These methods manage trace labels stored in the ``trace_labels``
ClickHouse table (ReplacingMergeTree).
"""

from __future__ import annotations

import logging

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.otel_traces import (
    LabelDeleteResponse,
    LabelItem,
    LabelPutRequest,
    LabelResponse,
)
from oxp.query_builders import labels as label_queries

logger = logging.getLogger(__name__)


class LabelsClient:
    """Labels operations mixed into :class:`LocalClient`."""

    db: Connector

    # ── GET ───────────────────────────────────────────────────────────────

    def get_label(self, session_id: str) -> LabelResponse:
        """Return the label for *session_id*, or ``None`` if not set."""
        query = label_queries.get_label_query(session_id)
        try:
            rows = self.db.execute(query)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get label for session '{session_id}': {exc}"
            ) from exc

        if not rows:
            return LabelResponse(session_id=session_id, label=None)

        r = rows[0]
        return LabelResponse(
            session_id=session_id,
            label=LabelItem(
                session_id=r[0],
                label=bool(r[1]),
                labeler=r[2],
                reason=r[3],
                updated_at=str(r[4]) if r[4] else None,
            ),
        )

    # ── PUT (upsert) ─────────────────────────────────────────────────────

    def put_label(
        self,
        session_id: str,
        body: LabelPutRequest,
    ) -> LabelResponse:
        """Create or update the label for *session_id*."""
        cmd = label_queries.upsert_label_query(
            session_id=session_id,
            label=body.label,
            labeler=body.labeler,
            reason=body.reason,
        )
        self.db.execute_command(cmd)
        return self.get_label(session_id)

    # ── DELETE ────────────────────────────────────────────────────────────

    def delete_label(self, session_id: str) -> LabelDeleteResponse:
        """Delete the label for *session_id*."""
        cmd = label_queries.delete_label_query(session_id)
        try:
            self.db.execute_command(cmd)
            return LabelDeleteResponse(session_id=session_id, deleted=True)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to delete label for session '{session_id}': {exc}"
            ) from exc
