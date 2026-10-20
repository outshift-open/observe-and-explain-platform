"""What a protocol detector is, and what it reports.

A detector answers two questions about one Cognition protocol in one session, from the
session's spans (what ``OXPKGProvider.fetch`` returns):

  enabled    was the protocol available to the session's agents?
  activated  did the agents actually use it?

and says which agents and skills are behind each answer. How it finds out is the
detector's own business: ``SkillProtocolDetector`` reads skill lists and skill
calls, another protocol can look for whatever shows it was present and used.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProtocolFinding:
    protocol: str
    enabled: bool = False
    activated: bool = False
    #: skills listed as available, by agent
    enabled_by_agent: dict[str, list[str]] = field(default_factory=dict)
    #: skills the agents called, by agent
    activated_by_agent: dict[str, list[str]] = field(default_factory=dict)
    #: how we know it was enabled, for example "system_prompt" or "activation"
    enabled_evidence: str = ""

    @property
    def skills_enabled(self) -> list[str]:
        return sorted({s for skills in self.enabled_by_agent.values() for s in skills})

    @property
    def skills_activated(self) -> list[str]:
        return sorted({s for skills in self.activated_by_agent.values() for s in skills})

    @property
    def agents_enabled(self) -> list[str]:
        return sorted(self.enabled_by_agent)

    @property
    def agents_activated(self) -> list[str]:
        return sorted(self.activated_by_agent)


@dataclass
class SessionSpans:
    """A session's spans, by kind, and which agent each span belongs to."""

    agents: list[dict[str, Any]]
    llms: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    #: span id of an agent call -> agent name; an LLM or tool span's ``parentSpanId`` is one of these
    owner: dict[str, str]

    @classmethod
    def of(cls, context: dict[str, Any]) -> SessionSpans:
        agents = context.get("agent_calls") or context.get("agent_spans") or []
        return cls(
            agents=agents,
            llms=context.get("llm_calls") or context.get("llm_spans") or [],
            tools=context.get("tool_calls") or context.get("tool_spans") or [],
            owner={str(s.get("spanId")): str(s.get("agentName")) for s in agents if s.get("spanId") and s.get("agentName")},
        )

    def agent_of(self, span: dict[str, Any]) -> str:
        return self.owner.get(str(span.get("parentSpanId")), "unknown")


class ProtocolDetector(ABC):
    """Detects one Cognition protocol in a session.

    Subclass it, give it a ``name`` (the protocol's name, as stored in the reports), and
    implement ``detect``. Register an instance with ``DetectorRegistry.register`` or, from
    another package, as an entry point in the ``cognition_protocol_detectors`` group.
    """

    #: the protocol's name, lower case, for example "accord"
    name: str = ""

    @abstractmethod
    def detect(self, context: dict[str, Any]) -> ProtocolFinding:
        """Read the protocol's presence and use off a session's spans (``SessionSpans.of(context)``)."""
