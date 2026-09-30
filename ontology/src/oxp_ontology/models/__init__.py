# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""Flat re-export of every generated KG node/edge model, plus the base classes.

Lets callers write ``from oxp_ontology.models import AgentCall`` instead of
``from oxp_ontology.models.nodes.agent_call import AgentCall``. Safe only
because node names (OWL classes, e.g. ``AgentCall``) and edge names (OWL
object properties, e.g. ``contains``) never collide in this ontology - if
that ever changes, disambiguate via ``oxp_ontology.models.nodes`` /
``oxp_ontology.models.edges`` instead.

Requires ``scripts/generate_models.py`` (or ``make generate-models``) to have
run first - ``nodes/`` and ``edges/`` are generated, not committed.
"""

from .base import KGBase as KGBase
from .base import KGEdge as KGEdge
from .base import KGNode as KGNode
from .edges import *  # noqa: F403
from .nodes import *  # noqa: F403
