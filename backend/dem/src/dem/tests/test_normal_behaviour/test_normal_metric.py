#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
import numpy as np
from dem.normal_behaviour.normal_metric import MetricNormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourResultMetric


def test_gaussian_normal_behaviour():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    nb = MetricNormalBehaviour(statistic="gaussian")
    result = nb.calculate_normal_behaviour(data)
    assert isinstance(result, NormalBehaviourResultMetric)
    assert result.upper is not None, "Upper bound should not be None"
    assert result.lower is not None, "Lower bound should not be None"
    assert result.std is not None, "Standard deviation should not be None"
    assert result.statistic != "", "Statistic description should not be empty"
    assert result.upper > result.lower, "Upper bound should be greater than lower bound"

    assert result.centroid == pytest.approx(np.mean(data)), (
        "Centroid should be the mean of the data"
    )
    assert result.lower == pytest.approx(np.mean(data) - 2 * np.std(data)), (
        "Lower bound should be mean - 2*std"
    )
    assert result.upper == pytest.approx(np.mean(data) + 2 * np.std(data)), (
        "Upper bound should be mean + 2*std"
    )
    assert result.std == pytest.approx(np.std(data)), (
        "Standard deviation should be correctly calculated"
    )


def test_quantiles_normal_behaviour():
    data = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    nb = MetricNormalBehaviour(statistic="quantiles")
    result = nb.calculate_normal_behaviour(data)
    assert isinstance(result, NormalBehaviourResultMetric), (
        "Result should be an instance of NormalBehaviourResultMetric"
    )
    assert result.statistic != "", "Statistic description should not be empty"
    # Quantile bounds should be within the data range
    assert min(data) <= (result.lower or 0) <= max(data), (
        "Lower quantile should be within the data range"
    )
    assert min(data) <= (result.upper or 0) <= max(data), (
        "Upper quantile should be within the data range"
    )
    assert (result.upper or 0) > (result.lower or 0), (
        "Upper quantile should be greater than lower quantile"
    )

    assert result.centroid == pytest.approx(np.median(data)), (
        "Centroid should be the median of the data"
    )
    assert result.lower == pytest.approx(np.quantile(data, 0.05)), (
        "Lower quantile should be approximately the 5th percentile of the data"
    )
    assert result.upper == pytest.approx(np.quantile(data, 0.95)), (
        "Upper quantile should be approximately the 95th percentile of the data"
    )


def test_var_normal_behaviour():
    data = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    nb = MetricNormalBehaviour(statistic="var_based")
    result = nb.calculate_normal_behaviour(data)
    assert isinstance(result, NormalBehaviourResultMetric), (
        "Result should be an instance of NormalBehaviourResultMetric"
    )
    assert result.statistic != "", "Statistic description should not be empty"
    # Variance-based bounds should be within the data range
    assert min(data) <= (result.lower or 0) <= max(data), (
        "Lower bound should be within the data range"
    )
    assert min(data) <= (result.upper or 0) <= max(data), (
        "Upper bound should be within the data range"
    )
    assert (result.upper or 0) > (result.lower or 0), (
        "Upper bound should be greater than lower bound"
    )
    assert result.mean == pytest.approx(np.mean(data)), (
        "Mean should be correctly calculated"
    )
    assert result.std == pytest.approx(np.std(data)), (
        "Standard deviation should be correctly calculated"
    )
    assert result.variance == pytest.approx(np.var(data)), (
        "Variance should be correctly calculated"
    )

    assert result.centroid == pytest.approx(np.mean(data)), (
        "Centroid should be the mean of the data"
    )
    assert result.upper == pytest.approx(np.mean(data) + np.std(data)), (
        "Upper bound should be mean + std"
    )
    assert result.lower == pytest.approx(np.mean(data) - np.std(data)), (
        "Lower bound should be mean - std"
    )


def test_empty_data_returns_default():
    nb = MetricNormalBehaviour(statistic="gaussian")
    result = nb.calculate_normal_behaviour([])
    assert isinstance(result, NormalBehaviourResultMetric), (
        "Result should be an instance of NormalBehaviourResultMetric"
    )
    assert result.statistic == "", (
        "Statistic description should be empty for empty data"
    )


def test_invalid_statistic_raises():
    nb = MetricNormalBehaviour(statistic="invalid")
    with pytest.raises(ValueError):
        nb.calculate_normal_behaviour([1, 2, 3])
