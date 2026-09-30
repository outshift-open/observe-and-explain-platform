#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Public API guardrails for the extracted norm package."""

from __future__ import annotations

import importlib.util


def test_completeness_helpers_are_not_public_library_modules() -> None:
    """Completeness is a test-layer invariant, not a product API surface."""
    assert importlib.util.find_spec("norm.completeness") is None
    assert importlib.util.find_spec("norm.native_completeness") is None
