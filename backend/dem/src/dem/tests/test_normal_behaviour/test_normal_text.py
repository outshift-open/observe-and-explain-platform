#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
import numpy as np
from dem.normal_behaviour.normal_textual import TextNormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourResultText

TEST_DATA = [
    np.array([2.0, 4.0, 8.0, 16.0, 32.0], dtype=float),  # centroid
    np.array([3.0, 4.0, 4.0, 16.0, 0.0], dtype=float),
    np.array([4.0, 4.0, 4.0, 16.0, 64.0], dtype=float),
    np.array([1.0, 6.0, 12.0, 16.0, 0.0], dtype=float),
    np.array([0.0, 2.0, 12.0, 16.0, 64.0], dtype=float),
]

RAW_DATA = ["sample1", "sample2", "sample3", "sample4", "sample5"]


def verify_centroid_calculation(
    result: NormalBehaviourResultText,
    expected_centroid: np.ndarray,
    expected_representative_data: str,
):
    assert isinstance(result.centroid, list), "Centroid should be a list for 2D data"
    assert len(result.centroid) == len(expected_centroid), (
        "Centroid length should match number of features"
    )
    for i in range(len(result.representative_sample)):
        assert result.representative_sample[i] == expected_centroid[i], (
            f"Centroid value for feature {i} should be correct"
        )

    assert result.representative_processed_sample == expected_representative_data, (
        "Representative data should match the expected value"
    )
    assert np.allclose(result.centroid, expected_centroid), (
        "Centroid should be close to the mean of the data"
    )


def test_gaussian_normal_behaviour():
    nb = TextNormalBehaviour(statistic="gaussian")
    result = nb.calculate_normal_behaviour(TEST_DATA, RAW_DATA)
    assert isinstance(result, NormalBehaviourResultText)
    assert isinstance(result.upper, list), "Upper bound should be a list for 2D data"
    assert isinstance(result.lower, list), "Lower bound should be a list for 2D data"
    assert isinstance(result.std, list), (
        "Standard deviation should be a list for 2D data"
    )
    assert result.statistic != "", "Statistic description should not be empty"

    verify_centroid_calculation(result, TEST_DATA[0], RAW_DATA[0])


def test_quantiles_normal_behaviour():
    nb = TextNormalBehaviour(statistic="quantiles")
    result = nb.calculate_normal_behaviour(TEST_DATA, RAW_DATA)
    assert isinstance(result, NormalBehaviourResultText)
    assert isinstance(result.upper, list), "Upper bound should be a list for 2D data"
    assert isinstance(result.lower, list), "Lower bound should be a list for 2D data"
    assert result.statistic != "", "Statistic description should not be empty"
    verify_centroid_calculation(result, TEST_DATA[0], RAW_DATA[0])


def test_var_normal_behaviour():
    nb = TextNormalBehaviour(statistic="var_based")
    result = nb.calculate_normal_behaviour(TEST_DATA, RAW_DATA)
    assert isinstance(result, NormalBehaviourResultText)
    assert isinstance(result.upper, list), "Upper bound should be a list for 2D data"
    assert isinstance(result.lower, list), "Lower bound should be a list for 2D data"
    assert isinstance(result.std, list), (
        "Standard deviation should be a list for 2D data"
    )
    assert result.statistic != "", "Statistic description should not be empty"
    verify_centroid_calculation(result, TEST_DATA[0], RAW_DATA[0])


def test_centroid_normal_behaviour():
    nb = TextNormalBehaviour(statistic="centroid")
    result = nb.calculate_normal_behaviour(TEST_DATA, RAW_DATA)
    assert isinstance(result, NormalBehaviourResultText)
    assert result.statistic != "", "Statistic description should not be empty"
    verify_centroid_calculation(result, TEST_DATA[0], RAW_DATA[0])


def test_density_normal_behaviour():
    nb = TextNormalBehaviour(statistic="density")
    result = nb.calculate_normal_behaviour(TEST_DATA, RAW_DATA)
    assert isinstance(result, NormalBehaviourResultText)
    assert result.statistic != "", "Statistic description should not be empty"
    verify_centroid_calculation(result, TEST_DATA[0], RAW_DATA[0])


def test_ellipse_normal_behaviour():
    nb = TextNormalBehaviour(statistic="ellipse")
    result = nb.calculate_normal_behaviour(TEST_DATA, RAW_DATA)
    assert isinstance(result, NormalBehaviourResultText)
    assert result.statistic != "", "Statistic description should not be empty"
    verify_centroid_calculation(result, TEST_DATA[0], RAW_DATA[0])


def test_empty_data_returns_default():
    nb = TextNormalBehaviour(statistic="gaussian")
    result = nb.calculate_normal_behaviour([], [])
    assert isinstance(result, NormalBehaviourResultText), (
        "Result should be an instance of NormalBehaviourResultText"
    )
    assert result.statistic == "", (
        "Statistic description should be empty for empty data"
    )


def test_invalid_statistic_raises():
    nb = TextNormalBehaviour(statistic="invalid")
    with pytest.raises(ValueError):
        nb.calculate_normal_behaviour(np.array([1, 2, 3]), np.array([1, 2, 3]))
