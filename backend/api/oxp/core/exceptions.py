#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXP application exceptions.

Each exception maps to an HTTP status code and carries enough context
for the centralized error handler to build a proper JSON response.
"""

from __future__ import annotations


class OXPError(Exception):
    """Base class for all OXP application errors."""

    status_code: int = 500

    def __init__(self, message: str = "Internal server error") -> None:
        self.message = message
        super().__init__(message)


class NotFoundError(OXPError):
    """Requested resource does not exist (404)."""

    status_code = 404

    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message)


class ValidationError(OXPError):
    """Client sent invalid or incomplete data (422)."""

    status_code = 422

    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message)


class DatabaseError(OXPError):
    """A database query failed (500)."""

    status_code = 500

    def __init__(self, message: str = "Database error") -> None:
        super().__init__(message)


class ConnectorError(OXPError):
    """Unable to reach a backend data store (503)."""

    status_code = 503

    def __init__(self, message: str = "Service unavailable") -> None:
        super().__init__(message)


class ExternalServiceError(OXPError):
    """A call to an external service (Neo4j, ClickHouse, …) failed (502)."""

    status_code = 502

    def __init__(self, message: str = "External service error") -> None:
        super().__init__(message)
