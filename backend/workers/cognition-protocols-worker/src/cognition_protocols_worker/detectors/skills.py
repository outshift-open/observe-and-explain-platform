"""Detect a protocol whose agents get it as skills with a common name prefix.

  enabled    an agent's system prompt lists one of the protocol's skills among its
             available skills, as a bullet ``- **l9-accord-initiator**: description``
  activated  one of the protocol's skills was actually called: ``activate_skill``
             with that name, or ``run_skill_script`` against it

Skill calls are matched on the raw argument text, so a call whose arguments were
cut short in storage is still seen as long as the skill name survived. A skill that
was called but is not listed in any readable prompt still counts as enabled (the
evidence is then recorded as ``"activation"``).
"""

from __future__ import annotations

import json
import re
from typing import Any

from .base import ProtocolDetector, ProtocolFinding, SessionSpans


def _text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, default=str) if value is not None else ""


def _system_text(prompt: Any) -> str:
    """The system messages of an LLM call's prompt (a JSON list of messages), or the prompt itself."""
    if isinstance(prompt, str):
        try:
            prompt = json.loads(prompt)
        except ValueError:
            return prompt
    if isinstance(prompt, list):
        return "\n".join(_text(m.get("content")) for m in prompt if isinstance(m, dict) and m.get("role") == "system")
    return _text(prompt)


class SkillProtocolDetector(ProtocolDetector):
    """A protocol whose skills are named ``<prefix>...``: ``SkillProtocolDetector("accord", "l9-accord-")``."""

    def __init__(self, name: str, *prefixes: str):
        if not prefixes:
            raise ValueError("a skill protocol needs at least one skill-name prefix")
        self.name = name
        self.prefixes = prefixes
        skill = "(?:" + "|".join(re.escape(p) for p in prefixes) + r")[\w.-]+"
        self._listed = re.compile(rf"^\s*[-*]\s*\*\*({skill})\*\*", re.MULTILINE)  # in a system prompt's skill list
        self._activated = re.compile(rf'"name"\s*:\s*"({skill})"')  # activate_skill arguments
        self._scripted = re.compile(rf'"skill"\s*:\s*"({skill})"')  # run_skill_script arguments

    def detect(self, context: dict[str, Any]) -> ProtocolFinding:
        spans = SessionSpans.of(context)
        found = ProtocolFinding(self.name)

        for span in spans.llms:
            listed = self._listed.findall(_system_text(span.get("prompt") or span.get("inputContent")))
            if listed:
                bucket = found.enabled_by_agent.setdefault(spans.agent_of(span), [])
                bucket.extend(s for s in listed if s not in bucket)

        for span in spans.tools:
            tool = str(span.get("toolName") or span.get("name") or "")
            arguments = _text(span.get("toolArguments") or span.get("inputContent") or span.get("inputParams"))
            pattern = self._activated if tool == "activate_skill" else self._scripted if tool == "run_skill_script" else None
            match = pattern.search(arguments) if pattern else None
            if match:
                bucket = found.activated_by_agent.setdefault(spans.agent_of(span), [])
                if match.group(1) not in bucket:
                    bucket.append(match.group(1))

        found.activated = bool(found.activated_by_agent)
        if found.enabled_by_agent:
            found.enabled, found.enabled_evidence = True, "system_prompt"
        elif found.activated:
            # Called, so it was there, even though no prompt we can read lists it.
            found.enabled, found.enabled_evidence = True, "activation"
        return found
