#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""The worker's rules: which events to call back about, and where.

What a rule *selects* is fixed by its ``name`` (see ``RULE_TYPES``); the file or the request
only says which rules are on, their ``callback_url`` and, for the rules that take one, the
``value`` they compare against. For example ``agent_events`` with ``value: researcher`` stands
for "events for the agent called researcher", and the same rule can be added once per agent.

Rules live in a ``RuleSet`` in the memory of the application. They are loaded from
``rules.yaml`` at startup and can be added or removed while it runs (``/rules``, see server.py).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "rules.yaml"

# name -> (what it selects, takes a value). How each one matches is in _MATCHERS below.
RULE_TYPES: dict[str, tuple[str, bool]] = {
    "all": ("Every event", False),
    "tool_events": ("All tool events", False),
    "tool_completed": ("Completed tool calls", False),
    "llm_events": ("All LLM events", False),
    "llm_completed": ("Completed LLM calls", False),
    "mcp_traffic": ("MCP traffic", False),
    "agent_handoffs": ("Agent handoffs only (excluding self-loops)", False),
    "service_events": ("Events from the service called `value`", True),
    "agent_events": ("Events for the agent called `value`", True),
}


def log_attributes(record: dict[str, Any]) -> dict[str, Any]:
    """The record's ``LogAttributes`` map (it may also arrive as a JSON string)."""
    attributes = record.get("LogAttributes")
    if isinstance(attributes, str):
        try:
            attributes = json.loads(attributes)
        except ValueError:
            return {}
    return attributes if isinstance(attributes, dict) else {}


def _event_name(attrs: dict[str, Any]) -> str:
    return str(attrs.get("event.name") or "")


# name -> does the log record match? ``attrs`` is its LogAttributes, ``value`` the rule's value.
_MATCHERS: dict[str, Callable[[dict[str, Any], dict[str, Any], str], bool]] = {
    "all": lambda record, attrs, value: True,
    "tool_events": lambda record, attrs, value: _event_name(attrs).startswith("tool."),
    "tool_completed": lambda record, attrs, value: _event_name(attrs) == "tool.completed",
    "llm_events": lambda record, attrs, value: _event_name(attrs).startswith("llm."),
    "llm_completed": lambda record, attrs, value: _event_name(attrs) == "llm.completed",
    "mcp_traffic": lambda record, attrs, value: attrs.get("network.protocol.name") == "mcp",
    "agent_handoffs": lambda record, attrs, value: (
        attrs.get("topology.edge.kind") == "agent_handoff"
        and attrs.get("source.agent") != attrs.get("target.agent")
    ),
    "service_events": lambda record, attrs, value: str(record.get("ServiceName") or "") == value,
    "agent_events": lambda record, attrs, value: value
    in (attrs.get("agent.name"), attrs.get("source.agent"), attrs.get("target.agent")),
}


@dataclass(frozen=True)
class Rule:
    name: str
    callback_url: str
    value: str = ""

    @property
    def key(self) -> str:
        """Identifies the rule: its name, plus the value for a rule that takes one."""
        return f"{self.name}={self.value}" if self.value else self.name

    def matches(self, record: dict[str, Any]) -> bool:
        """Does this log record (a flat row with ``LogAttributes``) match the rule?"""
        return _MATCHERS[self.name](record, log_attributes(record), self.value)

    def as_dict(self) -> dict[str, str]:
        data = {"name": self.name, "callback_url": self.callback_url}
        if self.value:
            data["value"] = self.value
        return data


def rule_from_dict(item: Any) -> Rule:
    """Build a rule from ``{name, callback_url[, value]}``, checking it against ``RULE_TYPES``."""
    if not isinstance(item, dict):
        raise ValueError(f"A rule is an object with a name and a callback_url: {item!r}")
    name = str(item.get("name") or "")
    callback_url = str(item.get("callback_url") or "")
    value = str(item.get("value") or "")
    if name not in RULE_TYPES:
        raise ValueError(f"Unknown rule {name!r}, expected one of {', '.join(RULE_TYPES)}")
    if not callback_url:
        raise ValueError(f"Rule {name!r} needs a callback_url")
    takes_value = RULE_TYPES[name][1]
    if takes_value and not value:
        raise ValueError(f"Rule {name!r} needs a value")
    if value and not takes_value:
        raise ValueError(f"Rule {name!r} takes no value")
    return Rule(name=name, callback_url=callback_url, value=value)


class RuleSet:
    """The rules by key, in the order they were added. Safe to use from several threads."""

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._lock = threading.Lock()
        self._rules: dict[str, Rule] = {}
        for rule in rules or []:
            self.add(rule)

    def add(self, rule: Rule) -> bool:
        """Add the rule, or replace the one with the same key (its callback URL changes).
        True if it is new."""
        with self._lock:
            new = rule.key not in self._rules
            self._rules[rule.key] = rule
            return new

    def remove(self, key: str) -> bool:
        with self._lock:
            return self._rules.pop(key, None) is not None

    def get(self, key: str) -> Rule | None:
        with self._lock:
            return self._rules.get(key)

    def __iter__(self) -> Iterator[Rule]:
        with self._lock:
            return iter(list(self._rules.values()))

    def __len__(self) -> int:
        with self._lock:
            return len(self._rules)

    def __contains__(self, key: object) -> bool:
        with self._lock:
            return key in self._rules

    def keys(self) -> list[str]:
        with self._lock:
            return list(self._rules)


def load_rules(path: Path = DEFAULT_RULES_PATH) -> RuleSet:
    """Read a rules file: a ``rules`` list of ``{name, callback_url[, value]}``."""
    with open(Path(path).expanduser(), encoding="utf-8") as f:
        content: Any = yaml.safe_load(f)
    items = content.get("rules") if isinstance(content, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"Expected a 'rules' list in {path}")
    rules = RuleSet()
    for item in items:
        rule = rule_from_dict(item)
        if rule.key in rules:
            raise ValueError(f"Duplicate rule {rule.key!r} in {path}")
        rules.add(rule)
    return rules
