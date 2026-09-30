#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""mce-helper — Abstract interfaces owned by MCE.

Three-layer architecture::

    mce-core   : pure computation engine, metric registry, no IO
    mce-helper : this package — MetricsProvider ABC (metric CRUD)
    oxp-api : concrete implementations (OXPKGProvider, OXPMetricsProvider)
                 also owns DataProvider ABC (KG-specific: resolve_session_id + fetch)
    mce-client : orchestration, provider injected by oxp-api
"""

from mce.helper.interfaces import MetricsProvider  # noqa: F401
from mce.helper.provider import MCEProvider  # noqa: F401  (backward compat alias)

__all__ = ["MetricsProvider", "MCEProvider"]
