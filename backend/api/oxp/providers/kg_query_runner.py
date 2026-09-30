#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Query execution helpers for ontology/workaround KG reads."""

from __future__ import annotations

import logging
from typing import Any, Callable

from oxp.connectors.base import Connector
from oxp.query_builders.types import QueryPair
from oxp.workarounds import KGWorkaroundsConfig

KGRow = dict[str, Any]
HasResults = Callable[[list[KGRow]], bool]


class KGQueryExecutionError(RuntimeError):
    """Raised when ontology and workaround KG queries both fail to execute."""

    def __init__(
        self,
        ctx: str,
        primary_error: Exception | None,
        fallback_error: Exception | None,
    ) -> None:
        details: list[str] = []
        if primary_error is not None:
            details.append(f"primary={primary_error}")
        if fallback_error is not None:
            details.append(f"fallback={fallback_error}")
        suffix = f": {', '.join(details)}" if details else ""
        super().__init__(
            f"KG query execution failed for {ctx or 'unknown context'}{suffix}"
        )
        self.ctx = ctx
        self.primary_error = primary_error
        self.fallback_error = fallback_error


class KGQueryRunner:
    """Execute KG queries with explicit ontology/workaround fallback."""

    def __init__(
        self,
        db: Connector,
        workarounds: KGWorkaroundsConfig,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        self._db = db
        self._workarounds = workarounds
        self._logger = logger or logging.getLogger(__name__)

    def execute(self, query: str, params: dict[str, Any] | None = None) -> list[KGRow]:
        """Execute a single KG query and normalize empty results."""
        rows = self._db.execute(query, params or {})
        return rows or []

    def execute_pair(
        self,
        ontology: QueryPair,
        workaround: QueryPair,
        *,
        has_results: HasResults | None = None,
        ctx: str = "",
    ) -> list[KGRow]:
        """Execute a query pair according to the configured workaround policy."""
        predicate = has_results or bool
        if self._workarounds.workarounds_first:
            primary, primary_label = workaround, "workaround"
            fallback, fallback_label = ontology, "ontology"
        else:
            primary, primary_label = ontology, "ontology"
            fallback, fallback_label = workaround, "workaround"

        primary_error: Exception | None = None

        try:
            rows = self.execute(*primary)
            if predicate(rows):
                self._logger.debug("[%s] %s query succeeded", ctx, primary_label)
                return rows
            self._logger.debug(
                "[%s] %s query returned empty, trying %s",
                ctx,
                primary_label,
                fallback_label,
            )
        except Exception as exc:
            self._logger.debug(
                "[%s] %s query raised: %s — trying %s",
                ctx,
                primary_label,
                exc,
                fallback_label,
            )
            primary_error = exc

        try:
            return self.execute(*fallback)
        except Exception as exc:
            self._logger.warning(
                "[%s] %s fallback also failed: %s",
                ctx,
                fallback_label,
                exc,
            )
            raise KGQueryExecutionError(ctx, primary_error, exc) from exc
