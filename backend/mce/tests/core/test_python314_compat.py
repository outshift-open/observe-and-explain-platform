#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Python 3.14 Compatibility Test

Verifies that MCE core functionality works on Python 3.14+.
"""

import sys
import pytest


def test_python_version_detection():
    """Verify Python version is correctly detected."""
    assert sys.version_info.major == 3
    assert sys.version_info.minor >= 11


def test_mce_import_without_deepeval():
    """Test that MCE core components import cleanly."""
    from mce.engine.engine import MetricEngine

    engine = MetricEngine()
    assert engine is not None


def test_deepeval_warning_on_python_314(monkeypatch):
    """Test that DeepEval provider issues warning on Python 3.14+."""
    import warnings

    if sys.version_info < (3, 14):
        pytest.skip("Test only relevant for Python 3.14+")

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        # Reset cache so warning path is executed even if earlier tests warmed it.
        from mce.providers.deepeval import provider as deepeval_provider

        monkeypatch.setattr(deepeval_provider, "_AdapterClass", None)

        deepeval_provider._get_adapter_class()

        # Check warning was issued
        assert len(w) > 0
        matching = [
            wm
            for wm in w
            if issubclass(wm.category, RuntimeWarning)
            and "not fully compatible with Python 3.14" in str(wm.message)
        ]
        assert matching, "Expected Python 3.14 DeepEval compatibility warning"


def test_native_metrics_work(monkeypatch):
    """Verify native metrics are always available."""
    from mce.core.registry import get_default_metrics

    metrics = get_default_metrics()

    metric_providers = {m.__class__.__module__ for m in metrics}
    native_present = any("native" in m or "sdk" in m for m in metric_providers)
    assert native_present, "Native/SDK metrics should always be discovered"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
