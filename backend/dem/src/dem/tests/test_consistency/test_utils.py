#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import numpy as np

from dem.consistency import ConsistencyResult


def test_consistency_result_defaults():
    """
    Test that ConsistencyResult initializes with correct default values.
    """
    result = ConsistencyResult()

    assert np.isnan(result.min)
    assert np.isnan(result.max)
    assert np.isnan(result.mean)
    assert np.isnan(result.confidence_interval[0])
    assert np.isnan(result.confidence_interval[1])
    assert result.confidence_indicator == ""
    assert result.statistic == ""


def test_consistency_result_valid_data():
    """
    Test that ConsistencyResult can be initialized with valid data.
    """
    result = ConsistencyResult(
        min=0.0,
        max=1.0,
        mean=0.75,
        confidence_interval=(0.7, 0.8),
        confidence_indicator="High",
        statistic="std",
    )

    assert result.min == 0.0
    assert result.max == 1.0
    assert result.mean == 0.75
    assert result.confidence_interval == (0.7, 0.8)
    assert result.confidence_indicator == "High"
    assert result.statistic == "std"


def test_consistency_result_partial_data():
    """
    Test that ConsistencyResult can be initialized with partial data,
    and defaults are applied for missing fields.
    """
    result = ConsistencyResult(mean=0.5, statistic="dispersion")

    assert np.isnan(result.min)
    assert np.isnan(result.max)
    assert result.mean == 0.5
    assert np.isnan(result.confidence_interval[0])
    assert np.isnan(result.confidence_interval[1])
    assert result.confidence_indicator == ""
    assert result.statistic == "dispersion"
