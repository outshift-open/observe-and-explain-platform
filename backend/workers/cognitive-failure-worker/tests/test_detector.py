#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json

import pytest
from cognitive_failure_worker.detector import (
    DetectionAnswer,
    DetectionItem,
    DetectorError,
    parse_detections,
)

CODES = {"IC-2", "CC-3"}
IDS = {"llmcall:1", "toolcall:2"}


def _answer(*items):
    return json.dumps({"detections": list(items)})


def _item(code="IC-2", confidence="medium", reasoning="why", call_id="llmcall:1"):
    return {"code": code, "confidence": confidence, "reasoning": reasoning, "call_id": call_id}


# ---------------------------------------------------------------- the answer


def test_valid_detections_are_kept():
    found = parse_detections(_answer(_item(), _item("CC-3", "high", "no reconciliation", None)), CODES, IDS)

    assert [(d.code, d.confidence, d.call_id) for d in found] == [
        ("IC-2", "medium", "llmcall:1"),
        ("CC-3", "high", None),
    ]


def test_json_wrapped_in_a_code_fence_is_read():
    assert len(parse_detections("```json\n" + _answer(_item()) + "\n```", CODES, IDS)) == 1


def test_no_detection_is_a_valid_answer():
    assert parse_detections(_answer(), CODES, IDS) == []


def test_code_and_confidence_are_normalised():
    (found,) = parse_detections(_answer(_item("ic-2", "HIGH")), CODES, IDS)

    assert (found.code, found.confidence) == ("IC-2", "high")


@pytest.mark.parametrize(
    "item",
    [
        _item("IR-1"),  # not asked for
        _item(confidence="certain"),
        _item(confidence=""),
        _item(reasoning=" "),
        "not an object",
    ],
    ids=["unasked code", "bad confidence", "no confidence", "no reasoning", "not an object"],
)
def test_an_invalid_detection_is_dropped_and_the_others_kept(item):
    found = parse_detections(_answer(item, _item("CC-3", call_id=None)), CODES, IDS)

    assert [d.code for d in found] == ["CC-3"]


def test_an_unknown_step_keeps_the_detection_on_the_session():
    (found,) = parse_detections(_answer(_item(call_id="llmcall:99")), CODES, IDS)

    assert found.call_id is None


@pytest.mark.parametrize("call_id", [None, "", "null"])
def test_no_step_means_the_session(call_id):
    assert parse_detections(_answer(_item(call_id=call_id)), CODES, IDS)[0].call_id is None


def test_the_same_failure_at_the_same_step_is_reported_once():
    found = parse_detections(_answer(_item(reasoning="first"), _item(reasoning="second")), CODES, IDS)

    assert [d.reasoning for d in found] == ["first"]


@pytest.mark.parametrize(
    "text", ["", "no json here", "{}", '{"detections": "none"}', '{"detections": {"a": 1}}', "[1, 2]"]
)
def test_an_unusable_answer_is_an_error(text):
    with pytest.raises(DetectorError):
        parse_detections(text, CODES, IDS)


# ---------------------------------------------------------------- the Pydantic model


def test_the_schema_describes_every_field_for_the_model():
    properties = DetectionAnswer.model_json_schema()["$defs"]["DetectionItem"]["properties"]

    assert all(p.get("description") for p in properties.values())
    assert properties["confidence"]["enum"] == ["low", "medium", "high"]


def test_an_item_is_normalised_by_the_model():
    item = DetectionItem.model_validate(
        {"code": " ic-2 ", "confidence": " MEDIUM ", "reasoning": " why ", "call_id": " llmcall:1 "}
    )

    assert item.model_dump() == {"code": "IC-2", "confidence": "medium", "reasoning": "why", "call_id": "llmcall:1"}


@pytest.mark.parametrize("call_id", [None, "", " ", "null", "None"])
def test_no_step_is_none(call_id):
    assert DetectionItem(code="IC-2", confidence="low", reasoning="x", call_id=call_id).call_id is None


def test_call_id_is_optional():
    assert DetectionItem.model_validate({"code": "IC-2", "confidence": "low", "reasoning": "x"}).call_id is None


@pytest.mark.parametrize(
    "item",
    [
        {"confidence": "low", "reasoning": "x"},
        {"code": "IC-2", "reasoning": "x"},
        {"code": "IC-2", "confidence": "low"},
        {"code": "IC-2", "confidence": "low", "reasoning": "  "},
        {"code": "IC-2", "confidence": "certain", "reasoning": "x"},
    ],
    ids=["no code", "no confidence", "no reasoning", "blank reasoning", "bad confidence"],
)
def test_an_item_missing_or_breaking_a_field_is_refused(item):
    with pytest.raises(ValueError):
        DetectionItem.model_validate(item)


def test_an_answer_built_from_the_model_round_trips():
    answer = DetectionAnswer(detections=[DetectionItem(code="CC-3", confidence="high", reasoning="no reconciliation")])

    found = parse_detections(answer.model_dump_json(), CODES, IDS)

    assert [(d.code, d.confidence, d.call_id) for d in found] == [("CC-3", "high", None)]
