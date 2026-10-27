#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""What the agent reports and how its answer is checked.

``DetectionAnswer`` is the schema of the ``submit_detections`` tool; ``parse_detections`` validates
what comes back against it and against the failures asked for and the steps of the trace. The
investigation itself is in ``agent.py``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

logger = logging.getLogger(__name__)

class DetectionItem(BaseModel):
    """One detection, as the model must report it. Its schema is what the model is asked to follow."""

    code: str = Field(description="Code of the detected failure, as given in its definition, e.g. IC-2.")
    confidence: Literal["low", "medium", "high"] = Field(
        description=(
            "high: the trace clearly meets every condition of the detection heuristic. "
            "medium: it meets the heuristic but one condition rests on inference. "
            "low: the evidence is plausible but weak or ambiguous."
        )
    )
    reasoning: str = Field(min_length=1, description="One or two sentences: what in the trace matches the failure.")
    call_id: str | None = Field(
        default=None,
        description="Id of the step where it happened, or null if it only shows across the whole session.",
    )

    @field_validator("code", "reasoning", mode="before")
    @classmethod
    def _strip(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", mode="after")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()

    @field_validator("confidence", mode="before")
    @classmethod
    def _lower(cls, value: Any) -> Any:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("call_id", mode="before")
    @classmethod
    def _no_step(cls, value: Any) -> Any:
        text = str(value).strip() if value is not None else ""
        return None if text in ("", "null", "None") else text


class DetectionAnswer(BaseModel):
    """What the model answers: the detections, possibly none."""

    detections: list[DetectionItem] = Field(description="The failures the trace shows. Empty if none.")


class _Envelope(BaseModel):
    """The answer with its detections not yet checked, so one bad detection does not lose the others."""

    detections: list[Any]


class DetectorError(RuntimeError):
    """The model's answer could not be used (not JSON, not the expected shape)."""


@dataclass(frozen=True)
class Detection:
    code: str
    confidence: str
    reasoning: str
    call_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "confidence": self.confidence, "reasoning": self.reasoning, "call_id": self.call_id}


@dataclass(frozen=True)
class DetectionResult:
    detections: list[Detection]
    prompt_tokens: int = 0
    completion_tokens: int = 0
    turns: int = 0


def render_failures(failures: Sequence[Mapping[str, Any]]) -> str:
    blocks = []
    for c in failures:
        signs = "\n".join(f"- {s}" for s in c["signature"])
        blocks.append(
            f"### {c['code']} — {c['name']} ({c['locus']}, {c['function']})\n{c['summary']}\n"
            f"Signs:\n{signs}\nDetect when: {c['heuristic']}"
        )
    return "\n\n".join(blocks)


def parse_detections(text: str, codes: set[str], step_ids: set[str]) -> list[Detection]:
    """The valid detections of the model's answer. Raises ``DetectorError`` if it is not the expected JSON.

    A detection that does not fit ``DetectionItem`` (an unknown confidence, no reasoning, ...) or whose
    failure was not asked for is dropped. A ``call_id`` that is not a step of the trace becomes ``None``
    (the detection stays, on the session).
    """
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        envelope = _Envelope.model_validate_json(match.group(0) if match else "")
    except ValidationError as exc:
        raise DetectorError(f"unusable answer ({exc.errors()[0]['msg']}): {(text or '')[:200]!r}") from exc

    detections: dict[tuple[str, str | None], Detection] = {}
    for raw in envelope.detections:
        try:
            item = DetectionItem.model_validate(raw)
        except ValidationError as exc:
            logger.warning("Dropping invalid detection %r: %s", raw, exc.errors()[0]["msg"])
            continue
        if item.code not in codes:
            logger.warning("Dropping detection of failure %s, which was not asked for", item.code)
            continue
        call_id = item.call_id
        if call_id is not None and call_id not in step_ids:
            logger.warning("Detection %s names unknown step %r; keeping it on the session", item.code, call_id)
            call_id = None
        detections.setdefault((item.code, call_id), Detection(item.code, item.confidence, item.reasoning, call_id))
    return list(detections.values())
