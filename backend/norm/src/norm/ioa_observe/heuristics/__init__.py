#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Post-processing passes that run once after every per-span handler --
see build.py for where these slot into the pipeline.
"""

from .capability_chain import chain_capability_calls
from .container_boundary_states import assign_container_boundary_states
from .handoff import chain_agent_handoffs_fallback, link_agent_handoffs

__all__ = [
    "assign_container_boundary_states",
    "chain_agent_handoffs_fallback",
    "chain_capability_calls",
    "link_agent_handoffs",
]
