#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import logging
import importlib
import threading
from mce.core.metric import Metric

logger = logging.getLogger(__name__)


class MetricRegistry:
    """
    Central Dynamic Registry for MCE Metrics.
    Allows Providers to register their metric implementations.
    """

    _instance = None
    _lock = threading.Lock()  # Guards singleton creation

    def __init__(self):
        self._metrics: dict[str, Metric] = {}
        self._by_class: dict[str, list[Metric]] = {}
        self._loaded_providers: set[str] = set()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # double-checked locking
                    cls._instance = MetricRegistry()
        return cls._instance

    def register(self, metric: Metric):
        """
        Register a metric instance.
        """
        if not isinstance(metric, Metric):
            raise TypeError(f"Expected Metric instance, got {type(metric)}")

        mid = metric.metric_id
        ontology = metric.ontology_class

        # 1. Register by ID
        if mid in self._metrics:
            logger.warning("Overwriting metric ID %r implementation.", mid)
        self._metrics[mid] = metric

        # 2. Register by Ontology Class
        if ontology not in self._by_class:
            self._by_class[ontology] = []

        # Avoid duplicates in list
        if metric not in self._by_class[ontology]:
            self._by_class[ontology].append(metric)

        logger.debug("Registered metric %r (%s)", mid, ontology)

    def get_metric(self, metric_id: str) -> Metric | None:
        return self._metrics.get(metric_id)

    def get_all(self) -> list[Metric]:
        return list(self._metrics.values())

    def get_by_class(self, ontology_class: str) -> list[Metric]:
        return self._by_class.get(ontology_class, [])

    def load_provider(self, module_name: str):
        """
        Dynamically import a provider module to trigger registration.
        The module is expected to have a 'register()' function or similar
        that registers its metrics with this singleton.
        """
        if module_name in self._loaded_providers:
            return

        try:
            mod = importlib.import_module(module_name)
            if hasattr(mod, "register"):
                mod.register(self)
                self._loaded_providers.add(module_name)
                logger.info("Loaded provider: %s", module_name)
            else:
                logger.warning(
                    "Provider module %r has no register() function.", module_name
                )
        except ImportError as e:
            logger.error("Failed to load provider %r: %s", module_name, e)
