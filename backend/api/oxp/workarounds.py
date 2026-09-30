#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Historical: ontology/workaround query-pair mechanism, now retired.

``oxp.providers.kg.OXPKGProvider`` used to run every KG read as an
(ontology-compliant query, workaround query) pair, controlled by
``KGWorkaroundsConfig``, to tolerate a graph that didn't yet follow the
ontology (missing ``hasMASCall``/``hasAgentCall``/``hasLLMCall``/
``hasToolCall`` relationships, ``Session`` nodes without timing, ToolCall
argument data under a legacy field name). That KG shape no longer exists --
``norm`` now writes the current ontology directly -- so every query builder
in ``oxp.query_builders.kg`` was migrated to a single, current-schema query
with no fallback, and ``OXPKGProvider`` no longer executes query pairs at
all.

``KGWorkaroundsConfig`` is kept here only because ``kg_query_runner.py``
(itself unused by any live path -- only its ``KGQueryExecutionError`` is
still imported, defensively, by ``api/api_v1/endpoints/metrics.py``) still
references it. Delete both once that defensive except clause is removed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class KGWorkaroundsConfig:
    """Vestigial -- see module docstring. Not consulted by OXPKGProvider."""

    workarounds_first: bool = False

    @classmethod
    def from_env(cls) -> "KGWorkaroundsConfig":
        """Build config from the ``MCE_WORKAROUNDS_FIRST`` environment variable."""
        wf = os.getenv("MCE_WORKAROUNDS_FIRST", "").strip().lower()
        return cls(workarounds_first=wf in ("1", "true", "yes"))
