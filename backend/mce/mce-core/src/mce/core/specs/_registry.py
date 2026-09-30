#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""MetricSpec — pure-data metric descriptor.
SpecRegistry — auto-discovering registry of MetricSpec objects.

Design principles
-----------------
* A ``MetricSpec`` is a *data artifact*, not behaviour.  It has no ``compute()``
  method and carries no runtime logic.  It describes *what* a metric is:
  its ontological identity, the data it consumes, and its classification.

* Concrete ``Metric`` subclasses link back to their spec via their
  ``metadata.name`` field — e.g. ``metadata.name = "AnswerRelevancy"`` means
  the implementation satisfies the ``AnswerRelevancy`` spec.

* One spec file per metric under ``mce/core/specs/``.  The registry discovers
  them automatically by scanning the package for module-level ``SPEC`` variables.

* ``mce metric list --abstract`` reads directly from ``SpecRegistry``, with no
  class instantiation and no dependency on the provider layer.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
import threading
from dataclasses import dataclass, field

from mce.core.metadata import MetricLayer, MetricNature, MetricScope
from mce.core.metric import MetricRequirements

logger = logging.getLogger(__name__)

# Name of the module-level variable that each spec file must expose.
_SPEC_VARIABLE = "SPEC"


@dataclass
class MetricSpec:
    """Pure-data descriptor for a single metric.

    Captures the *contract*: ontological identity, required inputs,
    classification.  Carries no computation logic.

    Parameters
    ----------
    name:
        Canonical metric identifier.  Must match the ``metadata.name`` of any
        concrete implementation that satisfies this spec.
    description:
        Human-readable description suitable for ``mce metric list --abstract``.
    layer:
        Abstraction layer (``MetricLayer``).
    nature:
        Computational nature — ``DETERMINISTIC`` or ``STOCHASTIC``.
    scope:
        Ontology scope the metric primarily applies to (``SESSION``,
        ``EXECUTION_ELEMENT``, etc.).
    ontology_class:
        Corresponding class name in ``mas-ontology.ttl``.
    input_requirements:
        Declarative description of the KG fields the metric consumes.
    version:
        Semantic version of this spec.  Implementations may define their own
        implementation version separately.
    tags:
        Optional set of free-form tags for grouping / filtering.
    """

    name: str
    description: str
    layer: MetricLayer
    nature: MetricNature
    scope: MetricScope
    ontology_class: str
    input_requirements: MetricRequirements = field(default_factory=MetricRequirements)
    version: str = "1.0.0"
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        """Serialise to a plain dict (e.g. for ``mce metric list --abstract --json``)."""
        return {
            "id": self.name,
            "description": self.description,
            "layer": self.layer.value,
            "nature": self.nature.value,
            "scope": self.scope.value,
            "ontology_class": self.ontology_class,
            "version": self.version,
            "input_requirements": {
                "text_fields": self.input_requirements.text_fields,
                "scalar_fields": self.input_requirements.scalar_fields,
                "vector_fields": self.input_requirements.vector_fields,
                "ground_truth": self.input_requirements.ground_truth,
            },
            "tags": list(self.tags),
        }

    @property
    def metadata(self):
        """Return a :class:`~mce.core.metadata.MetricMetadata` view of this spec.

        Allows ``MetricSpec`` to be used as a duck-type-compatible drop-in
        wherever code expects a ``Metric`` instance (e.g. ``format_metric_details``
        in the CLI).  The returned object is freshly constructed on each access —
        callers should not mutate it.
        """
        from mce.core.metadata import MetricMetadata, MetricImplementationType

        return MetricMetadata(
            name=self.name,
            description=self.description,
            layer=self.layer,
            nature=self.nature,
            scope=self.scope,
            ontology_class=self.ontology_class,
            version=self.version,
            implementation_type=MetricImplementationType.ABSTRACT,
        )


class SpecRegistry:
    """Auto-discovering registry of :class:`MetricSpec` objects.

    Discovery is lazy and cached — the first call to any classmethod triggers a
    package scan of ``mce.core.specs.*``.  Each module that exposes a
    module-level ``SPEC = MetricSpec(...)`` variable is registered automatically.

    Usage::

        from mce.core.specs import SpecRegistry

        all_specs = SpecRegistry.all_specs()          # sorted list of all specs
        spec      = SpecRegistry.get("AnswerRelevancy")  # single lookup
    """

    _specs: dict[str, MetricSpec] = {}
    _discovered: bool = False
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def _ensure_discovered(cls) -> None:
        if not cls._discovered:
            with cls._lock:
                if not cls._discovered:  # double-checked locking
                    cls.discover()

    @classmethod
    def discover(cls) -> None:
        """Walk ``mce.core.specs.*`` and register every module-level ``SPEC``."""
        import mce.core.specs as _pkg

        pkg_path = getattr(_pkg, "__path__", [])
        pkg_prefix = f"{_pkg.__name__}."
        found = 0

        for _, module_name, is_pkg in pkgutil.walk_packages(
            pkg_path, prefix=pkg_prefix
        ):
            if is_pkg:
                continue
            short = module_name.split(".")[-1]
            if short.startswith("_"):
                continue  # skip _registry, __init__
            try:
                mod = importlib.import_module(module_name)
                spec = getattr(mod, _SPEC_VARIABLE, None)
                if isinstance(spec, MetricSpec):
                    cls._specs[spec.name] = spec
                    found += 1
                else:
                    logger.debug("No SPEC found in %s — skipping.", module_name)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to load spec from %s: %s", module_name, exc)

        logger.debug("SpecRegistry: %d specs discovered.", found)
        cls._discovered = True

    @classmethod
    def all_specs(cls) -> list[MetricSpec]:
        """Return all discovered specs, sorted alphabetically by name."""
        cls._ensure_discovered()
        return sorted(cls._specs.values(), key=lambda s: s.name)

    @classmethod
    def get(cls, name: str) -> MetricSpec | None:
        """Return the spec for *name*, or ``None`` if not registered."""
        cls._ensure_discovered()
        return cls._specs.get(name)

    @classmethod
    def require(cls, name: str) -> "MetricSpec":
        """Return the spec for *name*, raising ``KeyError`` with a helpful message if absent.

        Use this in class bodies (``metadata = SpecRegistry.require("X").metadata``) so
        a missing or misspelled spec name fails loudly at import time instead of producing
        a confusing ``AttributeError: 'NoneType' ...'``.
        """
        cls._ensure_discovered()
        spec = cls._specs.get(name)
        if spec is None:
            available = sorted(cls._specs.keys())
            suffix = "..." if len(available) > 10 else ""
            raise KeyError(
                f"No spec registered for {name!r}. "
                f"Available ({len(available)}): {available[:10]}{suffix}"
            )
        return spec

    @classmethod
    def count(cls) -> int:
        """Number of registered specs."""
        cls._ensure_discovered()
        return len(cls._specs)

    @classmethod
    def _reset(cls) -> None:
        """Reset registry state.  For tests only."""
        with cls._lock:
            cls._specs = {}
            cls._discovered = False
