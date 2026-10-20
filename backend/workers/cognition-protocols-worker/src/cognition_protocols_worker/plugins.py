"""A registry of named plugins, with entry-point discovery.

Detectors and evaluators are both plugins keyed by protocol name. Built-ins are
registered in code. Installed packages add their own by declaring an entry point in the
registry's group; the target may be an instance, a subclass or a factory function.
"""

from __future__ import annotations

import inspect
import logging
from importlib.metadata import entry_points
from typing import Any, Generic, Iterable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def instantiate(target: Any, base: type) -> Any:
    """An entry point's target as a plugin: an instance, a subclass of ``base``, or a factory function."""
    if isinstance(target, base):
        return target
    if inspect.isclass(target) and issubclass(target, base):
        return target()
    if callable(target):
        return target()
    raise TypeError(f"{target!r} is not a {base.__name__}, a subclass of one, or a factory for one")


class Registry(Generic[T]):
    """Plugins by protocol name."""

    #: the base class every plugin derives from
    base: type = object
    #: the entry-point group installed packages register in
    group: str = ""

    def __init__(self, items: Iterable[T] = ()):
        self._items: dict[str, T] = {}
        for item in items:
            self.register(item)

    def register(self, item: T, *, replace: bool = False) -> None:
        name = getattr(item, "name", "")
        if not isinstance(item, self.base) or not name:
            raise TypeError(f"{item!r} is not a {self.base.__name__} with a name")
        if name in self._items and not replace:
            raise ValueError(f"a {self.base.__name__} for protocol {name!r} is already registered")
        self._items[name] = item

    def names(self) -> list[str]:
        return sorted(self._items)

    def items(self) -> list[T]:
        return [self._items[n] for n in self.names()]

    def get(self, name: str) -> T | None:
        return self._items.get(name)

    def load_entry_points(self) -> None:
        """Register what installed packages declare. A broken or clashing entry point is logged and skipped."""
        for entry in entry_points(group=self.group):
            try:
                item = instantiate(entry.load(), self.base)
                self.register(item)
            except Exception as exc:
                logger.error("%s plugin %r (%s) not loaded: %s", self.base.__name__, entry.name, entry.value, exc)
            else:
                logger.info("%s for protocol %r loaded from %s", self.base.__name__, item.name, entry.value)
