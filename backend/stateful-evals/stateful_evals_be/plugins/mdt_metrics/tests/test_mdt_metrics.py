#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from mdt_metrics import (
    GoalCoverage,
    Groundedness,
    IntentRecognitionAccuracy,
    OutcomeLegitimacy,
    PolicyActionCompliance,
    ResponseRelevance,
    StateConsistency,
)


def test_mdt_metric_default_names_are_namespaced():
    assert GoalCoverage().name == "GoalCoverage"
    assert Groundedness().name == "Groundedness"
    assert IntentRecognitionAccuracy().name == "IntentRecognitionAccuracy"
    assert OutcomeLegitimacy().name == "OutcomeLegitimacy"
    assert PolicyActionCompliance().name == "PolicyActionCompliance"
    assert ResponseRelevance().name == "ResponseRelevance"
    assert StateConsistency().name == "StateConsistency"


def test_mdt_metric_aggregation_level_is_span():
    assert GoalCoverage().aggregation_level == "span"
    assert Groundedness().aggregation_level == "span"
    assert IntentRecognitionAccuracy().aggregation_level == "span"
    assert OutcomeLegitimacy().aggregation_level == "span"
    assert PolicyActionCompliance().aggregation_level == "span"
    assert ResponseRelevance().aggregation_level == "span"
    assert StateConsistency().aggregation_level == "span"
