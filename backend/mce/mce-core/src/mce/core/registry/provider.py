#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import logging
from abc import ABC, abstractmethod

from mce.core.metric import Metric
from mce.core.registry import Registry

logger = logging.getLogger(__name__)


class Provider(ABC):
    """
    Abstract Base Class for Metric Providers.
    Each provider must implement this interface to register its metrics.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the provider (e.g. 'native', 'deepeval')."""
        pass

    @property
    @abstractmethod
    def metrics(self) -> list[Metric]:
        """List of metrics implemented by this provider that should be active."""
        pass

    def register(self, registry: Registry):
        """
        Dynamically registers all metrics from this provider into the Core Registry.
        This allows lazy loading and dynamic configuration.
        """
        logger.info(f"Loading provider: {self.name}...")
        for metric in self.metrics:
            logger.debug(f"  Registering metric: {metric.metric_id}")
            registry.register(metric)
        logger.info(f"Provider {self.name} loaded {len(self.metrics)} metrics.")
