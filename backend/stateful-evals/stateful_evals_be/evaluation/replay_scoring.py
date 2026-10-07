#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Replay scoring helpers for offline trajectory assumption testing.

This module re-scores saved per-trajectory evaluation artifacts without
re-running expensive LLM calls. The scoring knobs are intentionally
domain-agnostic so profiles can be validated across datasets.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence


@dataclass(frozen=True)
class ReplayScoringProfile:
    name: str
    description: str
    disable_response_drifting_gate: bool = False
    relax_response_drifting_when_tools_resolved: bool = False
    response_drifting_min_clusters: int = 1


@dataclass(frozen=True)
class ReplayScoringOutcome:
    predicted_label: int
    adjusted_unsatisfied_intents: int
    adjusted_fatal_failures: List[Dict[str, Any]]
    adjusted_minor_failures: List[Dict[str, Any]]
    quality_gate_failures: List[str]


REPLAY_PROFILES: Dict[str, ReplayScoringProfile] = {
    "legacy_current": ReplayScoringProfile(
        name="legacy_current",
        description="Mirror the pre-calibration trajectory scoring behavior.",
    ),
    "current": ReplayScoringProfile(
        name="current",
        description=(
            "Mirror the current in-code trajectory scoring behavior "
            "(response-drift relaxation)."
        ),
        relax_response_drifting_when_tools_resolved=True,
        response_drifting_min_clusters=2,
    ),
    "response_drift_relaxed": ReplayScoringProfile(
        name="response_drift_relaxed",
        description=(
            "Suppress response-span drifting gate when tool intents are resolved; "
            "keeps fatal/unsatisfied gating unchanged."
        ),
        relax_response_drifting_when_tools_resolved=True,
        response_drifting_min_clusters=2,
    ),
    "combined_relaxed": ReplayScoringProfile(
        name="combined_relaxed",
        description="Most permissive profile: disable the response-drift gate.",
        disable_response_drifting_gate=True,
    ),
}


def available_profiles() -> Dict[str, ReplayScoringProfile]:
    return REPLAY_PROFILES.copy()


def get_profile(name: str) -> ReplayScoringProfile:
    profile = REPLAY_PROFILES.get(name)
    if profile is None:
        available = ", ".join(sorted(REPLAY_PROFILES))
        raise ValueError(f"Unknown replay profile '{name}'. Available: {available}")
    return profile


def parse_profile_list(raw_profiles: str) -> List[ReplayScoringProfile]:
    names = [piece.strip() for piece in raw_profiles.split(",") if piece.strip()]
    if not names:
        names = ["current"]
    profiles = [get_profile(name) for name in names]
    deduped: Dict[str, ReplayScoringProfile] = {}
    for profile in profiles:
        deduped[profile.name] = profile
    return list(deduped.values())


def _is_response_state(state: Mapping[str, Any]) -> bool:
    return str(state.get("name", "")).startswith("response_span_")


def _is_transfer_fulfilled(intent_states: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        state.get("name") == "transfer_to_human_agents"
        and state.get("state") == "fulfilled"
        for state in intent_states
    )


def _tool_intent_resolution(
    intent_states: Sequence[Mapping[str, Any]],
) -> tuple[bool, bool]:
    tool_fulfilled = any(
        not _is_response_state(state) and state.get("state") == "fulfilled"
        for state in intent_states
    )
    tool_unresolved = any(
        not _is_response_state(state) and state.get("state") in {"failed", "drifting"}
        for state in intent_states
    )
    return tool_fulfilled, tool_unresolved


def _response_state_counts(
    intent_states: Sequence[Mapping[str, Any]],
) -> tuple[int, int]:
    drifting = sum(
        1
        for state in intent_states
        if _is_response_state(state) and state.get("state") == "drifting"
    )
    fulfilled = sum(
        1
        for state in intent_states
        if _is_response_state(state) and state.get("state") == "fulfilled"
    )
    return drifting, fulfilled


def _compute_quality_gate_reasons(
    *,
    result: Mapping[str, Any],
    unsatisfied_intents: int,
    fatal_failures: Sequence[Mapping[str, Any]],
    profile: ReplayScoringProfile,
) -> List[str]:
    reasons: List[str] = []
    if unsatisfied_intents > 0 or fatal_failures:
        return reasons

    intent_states = result.get("intent_states") or []
    transfer_fulfilled = _is_transfer_fulfilled(intent_states)
    tool_fulfilled, tool_unresolved = _tool_intent_resolution(intent_states)
    response_drifting, response_fulfilled = _response_state_counts(intent_states)
    total_response = response_drifting + response_fulfilled

    response_gate_enabled = not profile.disable_response_drifting_gate
    if (
        response_gate_enabled
        and profile.relax_response_drifting_when_tools_resolved
        and tool_fulfilled
        and not tool_unresolved
    ):
        response_gate_enabled = False

    if (
        response_gate_enabled
        and response_drifting >= profile.response_drifting_min_clusters
    ):
        if response_fulfilled == 0:
            reasons.append("response_span_drifting")
        elif total_response >= 3 and response_fulfilled / total_response < 0.20:
            reasons.append("response_span_drifting")

    minor_impacts = [
        str(detail.get("observed_impact", "none"))
        for detail in (result.get("minor_failures") or [])
    ]
    minor_count = len(minor_impacts)
    none_count = sum(1 for impact in minor_impacts if impact == "none")
    wrong_conclusion_count = sum(
        1 for impact in minor_impacts if impact == "wrong_conclusion"
    )
    wrong_action_count = sum(1 for impact in minor_impacts if impact == "wrong_action")

    total_spans = int(result.get("total_spans") or 1)
    minor_cluster_threshold = max(4, int(total_spans * 0.45))

    if (
        not transfer_fulfilled
        and minor_count >= minor_cluster_threshold
        and none_count == minor_count
    ):
        reasons.append("low_signal_minor_cluster")

    if not transfer_fulfilled and minor_count <= 5 and wrong_conclusion_count >= 3:
        reasons.append("dense_short_wrong_conclusion_cluster")

    if (
        not transfer_fulfilled
        and minor_count <= 5
        and none_count >= 4
        and wrong_conclusion_count >= 1
        and wrong_action_count == 0
    ):
        reasons.append("low_signal_short_cluster_with_wrong_conclusion")

    return reasons


def rescore_session_result(
    result: Mapping[str, Any],
    profile: ReplayScoringProfile,
) -> ReplayScoringOutcome:
    working_result = deepcopy(dict(result))

    fatal_failures = [
        deepcopy(detail) for detail in (working_result.get("fatal_failures") or [])
    ]
    minor_failures = [
        deepcopy(detail) for detail in (working_result.get("minor_failures") or [])
    ]
    unsatisfied_intents = int(working_result.get("unsatisfied_intents") or 0)

    quality_gate_failures = _compute_quality_gate_reasons(
        result=working_result,
        unsatisfied_intents=unsatisfied_intents,
        fatal_failures=fatal_failures,
        profile=profile,
    )

    predicted_label = (
        0
        if unsatisfied_intents > 0
        or len(fatal_failures) > 0
        or bool(quality_gate_failures)
        else 1
    )

    return ReplayScoringOutcome(
        predicted_label=predicted_label,
        adjusted_unsatisfied_intents=unsatisfied_intents,
        adjusted_fatal_failures=fatal_failures,
        adjusted_minor_failures=minor_failures,
        quality_gate_failures=quality_gate_failures,
    )
