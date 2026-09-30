#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Any, Protocol
from mce.core.metric import MetricRequirements
from mce.core.metadata import RetrievalRequest


class DataProvider(Protocol):
    def retrieve(self, request: RetrievalRequest) -> dict[str, Any]:
        """Execute a faceted retrieval request.

        Implementations should collapse the request into a single backend query
        whenever feasible, but may use multiple backend calls if necessary.
        """
        ...

    def fetch(
        self, resource_id: str, requirements: MetricRequirements
    ) -> dict[str, Any]:
        """Fetch data satisfying requirements for a single anchor resource.

        This compatibility method may translate metric requirements into a
        :class:`RetrievalRequest` and then delegate to :meth:`retrieve`.
        """
        ...

    def fetch_batch(
        self, resource_ids: list[str], requirements: MetricRequirements
    ) -> list[dict[str, Any]]:
        """Fetch data for multiple resources. Providers may implement this for efficiency.

        A default implementation looping over ``fetch`` is acceptable;
        the engine prefers this method when available.
        """
        return [self.fetch(rid, requirements) for rid in resource_ids]
