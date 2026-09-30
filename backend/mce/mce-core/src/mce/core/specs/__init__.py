#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Metric spec catalog — one file per metric, auto-discovered at first access.

Usage::

    from mce.core.specs import MetricSpec, SpecRegistry

    # All specs
    for spec in SpecRegistry.all_specs():
        print(spec.name, spec.nature.value)

    # Single lookup
    spec = SpecRegistry.get("AnswerRelevancy")
"""

from __future__ import annotations

from mce.core.specs._registry import MetricSpec, SpecRegistry

__all__ = ["MetricSpec", "SpecRegistry"]
