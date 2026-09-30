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
import re
from typing import Any, Dict, List, Mapping, Sequence

_PROCEDURAL_PRECONDITION_RE = re.compile(
    (
        r"(without first .*?(confirm|confirmation|authenticate|authentication))|"
        r"(without .* explicit .*confirmation)|"
        r"(required precondition)|"
        r"(required .*authentication)|"
        r"(obtain .*confirmation before)"
    ),
    re.IGNORECASE,
)
_HARD_WRONG_TARGET_RE = re.compile(
    (
        r"wrong (resource|record|target|entity|identifier|object)|"
        r"wrong [a-z_]*id\b|"
        r"mismatched? (id|identifier|target|entity)|"
        r"does not match (the )?(requested|target|identifier|input)|"
        r"incorrect (id|identifier|target|entity)"
    ),
    re.IGNORECASE,
)
_PROCEDURAL_PRECONDITION_DOWNGRADE_MARKER = (
    "Replay downgrade: procedural precondition violation profile."
)
_EMPTY_TEXT_RE = re.compile(r"\bempty\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReplayScoringProfile:
    name: str
    description: str
    disable_response_drifting_gate: bool = False
    relax_response_drifting_when_tools_resolved: bool = False
    response_drifting_min_clusters: int = 1
    downgrade_procedural_tool_fatals: bool = False
    clear_unsatisfied_if_only_downgraded_tool_intents: bool = False
    restore_downgraded_procedural_fatals: bool = False
    restore_high_score_threshold: float = 0.78
    restore_high_minor_max: int = 9
    restore_mid_score_threshold: float = 0.74
    restore_mid_minor_max: int = 5
    restore_low_score_threshold: float = 0.71
    restore_low_minor_max: int = 8
    restore_low_requires_no_wrong_conclusion: bool = True
    singleton_empty_response_relief: bool = False
    singleton_empty_response_minor_max: int = 8
    singleton_empty_response_fatality_max: float = 0.72


@dataclass(frozen=True)
class ReplayScoringOutcome:
    predicted_label: int
    adjusted_unsatisfied_intents: int
    adjusted_fatal_failures: List[Dict[str, Any]]
    adjusted_minor_failures: List[Dict[str, Any]]
    downgraded_fatal_failures: List[Dict[str, Any]]
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
            "(response-drift relaxation + selective procedural fatal calibration)."
        ),
        relax_response_drifting_when_tools_resolved=True,
        response_drifting_min_clusters=2,
        downgrade_procedural_tool_fatals=True,
        clear_unsatisfied_if_only_downgraded_tool_intents=True,
        restore_downgraded_procedural_fatals=True,
        restore_high_score_threshold=0.78,
        restore_high_minor_max=9,
        restore_mid_score_threshold=0.74,
        restore_mid_minor_max=5,
        restore_low_score_threshold=0.71,
        restore_low_minor_max=8,
        restore_low_requires_no_wrong_conclusion=True,
        singleton_empty_response_relief=True,
        singleton_empty_response_minor_max=20,
        singleton_empty_response_fatality_max=0.72,
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
    "procedural_fatal_relaxed": ReplayScoringProfile(
        name="procedural_fatal_relaxed",
        description=(
            "Downgrade procedural precondition tool fatals and clear unsatisfied "
            "tool intents tied only to downgraded spans."
        ),
        downgrade_procedural_tool_fatals=True,
        clear_unsatisfied_if_only_downgraded_tool_intents=True,
    ),
    "combined_relaxed": ReplayScoringProfile(
        name="combined_relaxed",
        description=(
            "Most permissive profile: disable response-drift gate and apply "
            "procedural fatal relaxation."
        ),
        disable_response_drifting_gate=True,
        downgrade_procedural_tool_fatals=True,
        clear_unsatisfied_if_only_downgraded_tool_intents=True,
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


def is_procedural_tool_precondition_fatal(detail: Mapping[str, Any]) -> bool:
    if str(detail.get("span_type", "")) != "tool":
        return False
    if str(detail.get("observed_impact", "none")) != "wrong_action":
        return False
    combined = (
        f"{detail.get('reasoning', '')} {detail.get('explanation', '')}"
    ).strip()
    if not _PROCEDURAL_PRECONDITION_RE.search(combined):
        return False
    if _HARD_WRONG_TARGET_RE.search(combined):
        return False
    return True


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


def _adjust_unsatisfied_intents(
    *,
    original_unsatisfied: int,
    intent_states: Sequence[Mapping[str, Any]],
    downgraded_spans: set[int],
    enabled: bool,
) -> int:
    if not enabled or original_unsatisfied <= 0 or not downgraded_spans:
        return original_unsatisfied

    unresolved_tool_states = [
        state
        for state in intent_states
        if (not _is_response_state(state))
        and state.get("state") in {"failed", "drifting"}
    ]
    if not unresolved_tool_states:
        return original_unsatisfied

    remaining_unresolved = 0
    for state in unresolved_tool_states:
        timeline = state.get("timeline") or []
        tool_spans = {
            int(event.get("span_index"))
            for event in timeline
            if event.get("span_type") == "tool" and event.get("span_index") is not None
        }
        failed_tool_spans: set[int] = set()
        for event in timeline:
            if event.get("span_type") != "tool" or event.get("span_index") is None:
                continue
            try:
                event_score = float(event.get("score") or 0.0)
            except (TypeError, ValueError):
                event_score = 0.0
            if event_score == 0.0:
                failed_tool_spans.add(int(event.get("span_index")))
        relevant_tool_spans = failed_tool_spans or tool_spans
        if relevant_tool_spans and relevant_tool_spans.issubset(downgraded_spans):
            continue
        remaining_unresolved += 1
    return remaining_unresolved


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
    intent_states = working_result.get("intent_states") or []

    downgraded_fatals: List[Dict[str, Any]] = []
    if profile.downgrade_procedural_tool_fatals and fatal_failures:
        retained_fatals: List[Dict[str, Any]] = []
        for detail in fatal_failures:
            if is_procedural_tool_precondition_fatal(detail):
                detail["explanation"] = (
                    f"{detail.get('explanation', '')} "
                    f"{_PROCEDURAL_PRECONDITION_DOWNGRADE_MARKER}"
                ).strip()
                downgraded_fatals.append(detail)
                minor_failures.append(detail)
            else:
                retained_fatals.append(detail)
        fatal_failures = retained_fatals

    downgraded_spans = {
        int(detail.get("span_index"))
        for detail in downgraded_fatals
        if detail.get("span_index") is not None
    }
    unsatisfied_intents = _adjust_unsatisfied_intents(
        original_unsatisfied=unsatisfied_intents,
        intent_states=intent_states,
        downgraded_spans=downgraded_spans,
        enabled=profile.clear_unsatisfied_if_only_downgraded_tool_intents,
    )

    if profile.restore_downgraded_procedural_fatals and downgraded_fatals:
        minor_impacts = [
            str(detail.get("observed_impact", "none")) for detail in minor_failures
        ]
        minor_count = len(minor_impacts)
        wrong_conclusion_minor_count = sum(
            1 for impact in minor_impacts if impact == "wrong_conclusion"
        )
        retained_downgraded: List[Dict[str, Any]] = []
        for detail in downgraded_fatals:
            explanation_text = str(detail.get("explanation", ""))
            if _PROCEDURAL_PRECONDITION_DOWNGRADE_MARKER not in explanation_text:
                retained_downgraded.append(detail)
                continue
            fatality_score = float(detail.get("fatality_score") or 0.0)
            should_restore = False
            if (
                fatality_score >= profile.restore_high_score_threshold
                and minor_count <= profile.restore_high_minor_max
            ):
                should_restore = True
            if (
                fatality_score >= profile.restore_mid_score_threshold
                and minor_count <= profile.restore_mid_minor_max
            ):
                should_restore = True
            if (
                fatality_score <= profile.restore_low_score_threshold
                and minor_count <= profile.restore_low_minor_max
                and (
                    not profile.restore_low_requires_no_wrong_conclusion
                    or wrong_conclusion_minor_count == 0
                )
            ):
                should_restore = True

            if should_restore:
                detail["explanation"] = (
                    f"{detail.get('explanation', '')} "
                    "Replay re-promotion: high-risk procedural precondition."
                ).strip()
                fatal_failures.append(detail)
            else:
                retained_downgraded.append(detail)
        downgraded_fatals = retained_downgraded

    if (
        profile.singleton_empty_response_relief
        and unsatisfied_intents == 0
        and len(fatal_failures) == 1
        and len(minor_failures) <= profile.singleton_empty_response_minor_max
    ):
        singleton_fatal = fatal_failures[0]
        singleton_text = (
            f"{singleton_fatal.get('reasoning', '')} "
            f"{singleton_fatal.get('explanation', '')}"
        )
        if (
            singleton_fatal.get("span_type") == "llm"
            and singleton_fatal.get("observed_impact") == "wrong_conclusion"
            and singleton_fatal.get("metric")
            in {"ResponseRelevance", "mdt.ResponseRelevance"}
            and float(singleton_fatal.get("fatality_score") or 0.0)
            <= profile.singleton_empty_response_fatality_max
            and _EMPTY_TEXT_RE.search(singleton_text)
        ):
            singleton_fatal["explanation"] = (
                f"{singleton_fatal.get('explanation', '')} "
                "Replay downgrade: singleton low-signal empty-response fatal."
            ).strip()
            minor_failures.append(singleton_fatal)
            fatal_failures = []

    # Feed adjusted failures into quality-gate evaluation.
    working_result["minor_failures"] = minor_failures
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
        downgraded_fatal_failures=downgraded_fatals,
        quality_gate_failures=quality_gate_failures,
    )
