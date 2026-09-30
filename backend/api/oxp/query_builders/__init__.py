#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXP query builders — one module per feature domain.

Example::

    from oxp.query_builders import ui

    stmt = ui.sessions_query(app_name="my-app")
"""

from oxp.query_builders.types import Dialect, QueryAndParams

__all__ = ["Dialect", "QueryAndParams"]
