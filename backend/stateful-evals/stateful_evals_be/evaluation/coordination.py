#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Normalized coordination topology and provenance for trajectory evaluation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

COORDINATION_CONTEXT_ATTRIBUTE = "stateful_evals.coordination.context"

TOPOLOGIES = frozenset(
    {
        "centralized_moderator",
        "hybrid_moderator",
        "hybrid_multi_round",
        "independent_parallel",
        "sequential_pipeline",
        "staged_debate",
        "unknown",
    }
)

_ALIASES = {
    "centralized": "centralized_moderator",
    "centralized_moderator": "centralized_moderator",
    "deterministic_linear": "sequential_pipeline",
    "deterministic_parallel": "independent_parallel",
    "deterministic_staged_debate": "staged_debate",
    "hybrid": "hybrid_moderator",
    "hybrid_moderator": "hybrid_moderator",
    "hybrid_multi_round": "hybrid_multi_round",
    "independent": "independent_parallel",
    "independent_parallel": "independent_parallel",
    "sequential": "sequential_pipeline",
    "sequential_pipeline": "sequential_pipeline",
    "staged_debate": "staged_debate",
}


def normalize_topology(value: Any) -> str | None:
    """Normalize a declared topology without guessing from arbitrary text."""
    raw = str(value or "").strip().casefold().replace("-", "_").replace(" ", "_")
    if not raw:
        return None
    return _ALIASES.get(raw)


def _text(value: Any, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit]}…"


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class CoordinationEdge:
    """One observed inter-component request/response boundary."""

    edge_id: str
    call_id: str
    sender: str
    receiver: str
    dispatcher: str
    request: str
    response: str
    start_event_index: int
    end_event_index: int
    start_timestamp: float
    end_timestamp: float
    stage_index: int
    round_index: int
    relation: str = "delegation"
    source_span_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class VerificationProvenance:
    """Observed verifier interaction and its relationship to later action."""

    edge_id: str
    stage_index: int
    round_index: int
    sender: str
    receiver: str
    dispatcher: str
    verdict: str
    action_after_verification: bool
    verification_gate_observed: bool


@dataclass
class CoordinationContext:
    """Framework-neutral coordination artifacts supplied by telemetry adapters."""

    schema_version: str = "coordination-context.v1"
    declared_topology: str | None = None
    declared_topology_source: str | None = None
    inferred_topology: str = "unknown"
    topology_verification: str = "not_provided"
    inference_confidence: str = "low"
    inference_method: str = "no_coordination_edges_observed"
    inference_signals: list[str] = field(default_factory=list)
    inference_ambiguities: list[str] = field(default_factory=list)
    edges: list[CoordinationEdge] = field(default_factory=list)
    verification: VerificationProvenance | None = None
    final_response: str = ""
    final_response_event_index: int = -1

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    def compact_payload(self) -> dict[str, Any]:
        """Return bounded topology evidence suitable for metric judge payloads."""
        return {
            "schema_version": self.schema_version,
            "declared_topology": self.declared_topology,
            "declared_topology_source": self.declared_topology_source,
            "inferred_topology": self.inferred_topology,
            "topology_verification": self.topology_verification,
            "inference_confidence": self.inference_confidence,
            "inference_method": self.inference_method,
            "inference_signals": list(self.inference_signals),
            "inference_ambiguities": list(self.inference_ambiguities),
            "edges": [
                {
                    "edge_id": edge.edge_id,
                    "sender": edge.sender,
                    "receiver": edge.receiver,
                    "dispatcher": edge.dispatcher,
                    "stage_index": edge.stage_index,
                    "round_index": edge.round_index,
                    "relation": edge.relation,
                    "source_span_ids": list(edge.source_span_ids),
                    "request": _text(edge.request, limit=600),
                    "response": _text(edge.response, limit=600),
                }
                for edge in self.edges
            ],
            "verification": (
                asdict(self.verification) if self.verification is not None else None
            ),
        }

    def topology_payload(self) -> dict[str, Any]:
        """Return topology diagnostics without duplicating canonical artifacts."""
        return {
            "schema_version": self.schema_version,
            "declared_topology": self.declared_topology,
            "declared_topology_source": self.declared_topology_source,
            "inferred_topology": self.inferred_topology,
            "topology_verification": self.topology_verification,
            "inference_confidence": self.inference_confidence,
            "inference_method": self.inference_method,
            "inference_signals": list(self.inference_signals),
            "inference_ambiguities": list(self.inference_ambiguities),
        }

    def result_metadata(self, metric_code: str | None = None) -> dict[str, Any]:
        """Return topology diagnostics without duplicating artifact provenance."""
        del metric_code
        verification = asdict(self.verification) if self.verification else None
        return {
            "topology": {
                "declared": self.declared_topology,
                "declared_source": self.declared_topology_source,
                "inferred": self.inferred_topology,
                "verification": self.topology_verification,
                "confidence": self.inference_confidence,
                "method": self.inference_method,
                "signals": list(self.inference_signals),
                "ambiguities": list(self.inference_ambiguities),
            },
            "verification_provenance": verification,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> CoordinationContext:
        if not isinstance(payload, Mapping):
            return cls()
        edges = []
        for item in payload.get("edges") or []:
            if not isinstance(item, Mapping):
                continue
            edges.append(
                CoordinationEdge(
                    edge_id=str(item.get("edge_id") or ""),
                    call_id=str(item.get("call_id") or ""),
                    sender=str(item.get("sender") or "unknown"),
                    receiver=str(item.get("receiver") or "unknown"),
                    dispatcher=str(item.get("dispatcher") or "unknown"),
                    request=str(item.get("request") or ""),
                    response=str(item.get("response") or ""),
                    start_event_index=_integer(item.get("start_event_index"), -1),
                    end_event_index=_integer(item.get("end_event_index"), -1),
                    start_timestamp=float(item.get("start_timestamp") or 0),
                    end_timestamp=float(item.get("end_timestamp") or 0),
                    stage_index=_integer(item.get("stage_index"), 0),
                    round_index=_integer(item.get("round_index"), 1),
                    relation=str(item.get("relation") or "delegation"),
                    source_span_ids=tuple(
                        str(span_id)
                        for span_id in item.get("source_span_ids") or []
                        if span_id
                    ),
                )
            )
        raw_verification = payload.get("verification")
        verification = None
        if isinstance(raw_verification, Mapping):
            verification = VerificationProvenance(
                edge_id=str(raw_verification.get("edge_id") or ""),
                stage_index=_integer(raw_verification.get("stage_index"), 0),
                round_index=_integer(raw_verification.get("round_index"), 1),
                sender=str(raw_verification.get("sender") or "unknown"),
                receiver=str(raw_verification.get("receiver") or "unknown"),
                dispatcher=str(raw_verification.get("dispatcher") or "unknown"),
                verdict=str(raw_verification.get("verdict") or "UNKNOWN"),
                action_after_verification=bool(
                    raw_verification.get("action_after_verification")
                ),
                verification_gate_observed=bool(
                    raw_verification.get("verification_gate_observed")
                ),
            )
        inferred = str(
            payload.get("inferred_topology")
            or payload.get("observed_topology")
            or "unknown"
        )
        if inferred not in TOPOLOGIES:
            inferred = "unknown"
        return cls(
            schema_version=str(
                payload.get("schema_version") or "coordination-context.v1"
            ),
            declared_topology=normalize_topology(payload.get("declared_topology")),
            declared_topology_source=(
                str(payload.get("declared_topology_source"))
                if payload.get("declared_topology_source")
                else None
            ),
            inferred_topology=inferred,
            topology_verification=str(
                payload.get("topology_verification") or "not_provided"
            ),
            inference_confidence=str(payload.get("inference_confidence") or "low"),
            inference_method=str(
                payload.get("inference_method") or "no_coordination_edges_observed"
            ),
            inference_signals=[
                str(item) for item in payload.get("inference_signals") or []
            ],
            inference_ambiguities=[
                str(item) for item in payload.get("inference_ambiguities") or []
            ],
            edges=edges,
            verification=verification,
            final_response=str(payload.get("final_response") or ""),
            final_response_event_index=_integer(
                payload.get("final_response_event_index"), -1
            ),
        )
