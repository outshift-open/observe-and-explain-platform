#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for the centralized exception handling.

Verifies that:
1. OXPError subclasses produce the correct HTTP status + JSON body.
2. Unhandled exceptions produce a generic 500 without leaking internals.
3. Stack traces are logged for all error categories.

Run with:
    pytest tests/test_exceptions.py -v -s
"""

import logging
import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from oxp.api import app
from oxp.core.exceptions import (
    OXPError,
    ConnectorError,
    DatabaseError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from fastapi import APIRouter
from fastapi.testclient import TestClient

# ── Temporary test routes ────────────────────────────────────────────────────
# We mount a test router that intentionally raises each exception type.

_test_router = APIRouter(prefix="/test-errors", tags=["test-errors"])


@_test_router.get("/not-found")
def raise_not_found():
    raise NotFoundError("Widget 42 does not exist")


@_test_router.get("/validation")
def raise_validation():
    raise ValidationError("'email' is required")


@_test_router.get("/database")
def raise_database():
    raise DatabaseError("connection refused on port 9000")


@_test_router.get("/connector")
def raise_connector():
    raise ConnectorError("ClickHouse is unreachable")


@_test_router.get("/external")
def raise_external():
    raise ExternalServiceError("Neo4j timed out after 30s")


@_test_router.get("/generic")
def raise_generic():
    raise OXPError("something went wrong")


@_test_router.get("/unhandled")
def raise_unhandled():
    raise RuntimeError("unexpected null pointer")


@_test_router.get("/unhandled-value")
def raise_unhandled_value():
    # Simulates a bug deep in a query builder
    return 1 / 0


app.include_router(_test_router)

client = TestClient(app, raise_server_exceptions=False)


# ── Exception → status code tests ───────────────────────────────────────────


class TestOXPErrorResponses:
    """Each OXPError subclass should return its mapped status code."""

    def test_not_found_returns_404(self):
        resp = client.get("/test-errors/not-found")
        assert resp.status_code == 404
        assert resp.json() == {"detail": "Widget 42 does not exist"}

    def test_validation_returns_422(self):
        resp = client.get("/test-errors/validation")
        assert resp.status_code == 422
        assert resp.json() == {"detail": "'email' is required"}

    def test_database_returns_500(self):
        resp = client.get("/test-errors/database")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "connection refused on port 9000"}

    def test_connector_returns_503(self):
        resp = client.get("/test-errors/connector")
        assert resp.status_code == 503
        assert resp.json() == {"detail": "ClickHouse is unreachable"}

    def test_external_service_returns_502(self):
        resp = client.get("/test-errors/external")
        assert resp.status_code == 502
        assert resp.json() == {"detail": "Neo4j timed out after 30s"}

    def test_base_oxp_error_returns_500(self):
        resp = client.get("/test-errors/generic")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "something went wrong"}


# ── Unhandled exception tests ────────────────────────────────────────────────


class TestUnhandledExceptions:
    """Unexpected errors should return 500 without leaking details."""

    def test_runtime_error_returns_generic_500(self):
        resp = client.get("/test-errors/unhandled")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Internal server error"}

    def test_zero_division_returns_generic_500(self):
        resp = client.get("/test-errors/unhandled-value")
        assert resp.status_code == 500
        assert resp.json() == {"detail": "Internal server error"}


# ── Logging tests ────────────────────────────────────────────────────────────


class TestErrorLogging:
    """Verify that errors are logged with stack traces."""

    def test_oxp_error_is_logged(self, caplog):
        with caplog.at_level(logging.ERROR, logger="oxp.api"):
            client.get("/test-errors/not-found")
        assert "NotFoundError" in caplog.text
        assert "Widget 42 does not exist" in caplog.text
        # Minimal stack trace should be present
        assert "Traceback" in caplog.text

    def test_unhandled_error_is_logged(self, caplog):
        with caplog.at_level(logging.ERROR, logger="oxp.api"):
            client.get("/test-errors/unhandled")
        assert "RuntimeError" in caplog.text
        assert "unexpected null pointer" in caplog.text
        assert "Traceback" in caplog.text

    def test_unhandled_error_does_not_leak_details(self, caplog):
        """The JSON body must NOT contain the real error message."""
        with caplog.at_level(logging.ERROR, logger="oxp.api"):
            resp = client.get("/test-errors/unhandled")
        # Logged internally
        assert "unexpected null pointer" in caplog.text
        # NOT leaked to the client
        assert "unexpected null pointer" not in resp.text


# ── Exception class unit tests ───────────────────────────────────────────────


class TestExceptionClasses:
    """Basic sanity checks on the exception hierarchy."""

    def test_all_subclass_oxp_error(self):
        for cls in (
            NotFoundError,
            ValidationError,
            DatabaseError,
            ConnectorError,
            ExternalServiceError,
        ):
            assert issubclass(cls, OXPError)

    def test_default_messages(self):
        assert NotFoundError().message == "Resource not found"
        assert ValidationError().message == "Validation error"
        assert DatabaseError().message == "Database error"
        assert ConnectorError().message == "Service unavailable"
        assert ExternalServiceError().message == "External service error"
        assert OXPError().message == "Internal server error"

    def test_custom_messages(self):
        e = DatabaseError("timeout after 5s")
        assert e.message == "timeout after 5s"
        assert str(e) == "timeout after 5s"
        assert str(e) == "timeout after 5s"

    def test_status_codes(self):
        assert NotFoundError.status_code == 404
        assert ValidationError.status_code == 422
        assert DatabaseError.status_code == 500
        assert ConnectorError.status_code == 503
        assert ExternalServiceError.status_code == 502
        assert OXPError.status_code == 500
