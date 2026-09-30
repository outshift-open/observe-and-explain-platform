#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""SQLAlchemy connector (works with SQLite, PostgreSQL, and other SA-supported engines)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from oxp.connectors.base import Connector

logger = logging.getLogger(__name__)


class SQLAlchemyConnector(Connector):
    """Manages a database connection via SQLAlchemy."""

    def __init__(
        self,
        url: str = "sqlite:///oxp.db",
        echo: bool = False,
        **engine_kwargs: Any,
    ):
        self._url = url
        self._echo = echo
        self._engine_kwargs = engine_kwargs
        self._engine: Any = None  # sqlalchemy.engine.Engine
        self._session_factory: Any = None  # sqlalchemy.orm.sessionmaker

    # ── lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        self._engine = create_engine(self._url, echo=self._echo, **self._engine_kwargs)
        self._session_factory = sessionmaker(bind=self._engine)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            self._session_factory = None

    def is_connected(self) -> bool:
        if self._engine is None:
            return False
        try:
            with self._engine.connect() as conn:
                conn.execute(self._text("SELECT 1"))
            return True
        except Exception as exc:
            logger.warning("SQLAlchemy connection check failed: %s", exc)
            return False

    # ── query execution ───────────────────────────────────────────────────

    def execute(self, query: Any, params: Optional[Dict[str, Any]] = None) -> List:
        """Execute a read query and return a list of row tuples.

        *query* may be a raw SQL string **or** a SQLAlchemy Core
        ``Select`` / ``TextClause`` statement.
        """
        self.ensure_connected()
        if logger.isEnabledFor(logging.DEBUG):
            if isinstance(query, str):
                logger.debug("Executing query: %s", query)
            else:
                try:
                    compiled = query.compile(
                        self._engine,
                        compile_kwargs={"literal_binds": True},
                    )
                    logger.debug(
                        "Executing query: \n***********************\n%s",
                        compiled.string,
                    )
                except Exception:
                    # Some types (e.g. expanding IN) can't render literal binds;
                    # fall back to showing query + params separately.
                    compiled = query.compile(
                        self._engine,
                        compile_kwargs={"literal_binds": False},
                    )
                    logger.debug(
                        "Executing query: %s | params: %s",
                        compiled.string,
                        compiled.params,
                    )
        session = self._session_factory()
        try:
            stmt = self._text(query) if isinstance(query, str) else query
            result = session.execute(stmt, params or {})
            return result.fetchall()
        finally:
            session.close()

    def execute_command(
        self, command: str, params: Optional[Dict[str, Any]] = None
    ) -> None:
        """Execute a DDL/DML command (INSERT, DELETE, CREATE TABLE, …)."""
        self.ensure_connected()
        session = self._session_factory()
        try:
            session.execute(self._text(command), params or {})
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ── helpers ───────────────────────────────────────────────────────────

    @property
    def engine(self):
        """Expose the underlying SQLAlchemy engine (e.g. for ``metadata.create_all``)."""
        self.ensure_connected()
        return self._engine

    def get_session(self):
        """Return a new SQLAlchemy :class:`~sqlalchemy.orm.Session`."""
        self.ensure_connected()
        return self._session_factory()

    @staticmethod
    def _text(sql: str):
        """Wrap a raw SQL string with :func:`sqlalchemy.text`."""
        from sqlalchemy import text

        return text(sql)
