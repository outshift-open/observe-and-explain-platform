#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Tests for mce.providers.native.metrics.quality package."""

from mce.providers.native.metrics.quality import (
    ResponseCompleteness,
    ResponseCompletenessV2,
)


class TestResponseCompleteness:
    def test_metadata(self):
        m = ResponseCompleteness()
        assert m.metadata.name is not None

    def test_compute_returns_result(self):
        m = ResponseCompleteness()
        ctx = {"input": "What is 2+2?", "output": "4", "session_id": "s1"}
        result = m.compute("entity1", ctx)
        assert result.resource_id == "entity1"
        assert result.value is not None

    def test_compute_empty_context(self):
        m = ResponseCompleteness()
        result = m.compute("e1", {})
        assert result is not None


class TestResponseCompletenessV2:
    def test_metadata(self):
        m = ResponseCompletenessV2()
        assert m.metadata.name is not None

    def test_compute_returns_result(self):
        m = ResponseCompletenessV2()
        ctx = {"input": "What is 2+2?", "output": "4"}
        result = m.compute("entity1", ctx)
        assert result is not None
        assert result.resource_id == "entity1"
