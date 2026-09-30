#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

import numpy as np
import pytest

from dem.consistency import ConsistencyResult, MetricConsistency


@pytest.fixture
def metric_consistency_instance():
    return MetricConsistency(
        confidence_level=95,
        sample_size=5,
        N_nearest_neighbors=10,
        N_bootstrap_samples=100,
    )


class TestMetricConsistency:
    def test_initialization(self, metric_consistency_instance):
        assert isinstance(metric_consistency_instance, MetricConsistency)
        assert metric_consistency_instance.confidence_level == 95
        assert metric_consistency_instance.sample_size == 5

    def test_calculate_std_statistic(self, metric_consistency_instance):
        bootstrap_samples = np.array(
            [
                [1, 2, 3, 4, 5],  # std = 1.414...
                [10, 10, 10, 10, 10],  # std = 0
                [0, 1, 2, 3, 4],  # std = 1.414...
            ]
        )
        sample = np.array([])

        stds = metric_consistency_instance._calculate_std_statistic(
            sample, bootstrap_samples
        )
        assert isinstance(stds, np.ndarray)
        assert stds.shape == (3,)
        assert np.isclose(stds[0], np.std([1, 2, 3, 4, 5]))
        assert np.isclose(stds[1], 0.0)
        assert np.isclose(stds[2], np.std([0, 1, 2, 3, 4]))

    @patch.object(MetricConsistency, "_calculate_consistency_with_confidence")
    @patch.object(MetricConsistency, "_format_consistency_result")
    def test_calculate_consistency_basic(
        self,
        mock_format_consistency_result,
        mock_calculate_consistency_with_confidence,
        metric_consistency_instance,
    ):
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        mock_calculate_consistency_with_confidence.return_value = {
            "mean": 0.5,
            "confidence_interval": (0.4, 0.6),
        }
        mock_format_consistency_result.return_value = ConsistencyResult(
            mean=0.9, confidence_interval=(0.8, 1.0)
        )

        result = metric_consistency_instance.calculate_consistency(data)

        mock_calculate_consistency_with_confidence.assert_called_once()
        _args, kwargs = mock_calculate_consistency_with_confidence.call_args
        assert np.array_equal(kwargs["sample"], np.asarray(data))

        mock_format_consistency_result.assert_called_once()
        args, kwargs = mock_format_consistency_result.call_args
        assert args[0] == {"mean": 0.5, "confidence_interval": (0.4, 0.6)}
        assert np.isclose(args[1], np.max(data) - np.min(data))  # max_score = 9.0

        assert isinstance(result, ConsistencyResult)
        assert result.mean == 0.9

    def test_calculate_consistency_empty_data(self, metric_consistency_instance):
        data = []
        result = metric_consistency_instance.calculate_consistency(data)
        assert isinstance(result, ConsistencyResult)
        assert np.isnan(result.mean)
        assert np.isnan(result.confidence_interval[0])

    @patch.object(MetricConsistency, "_calculate_consistency_with_confidence")
    @patch.object(MetricConsistency, "_format_consistency_result")
    def test_calculate_consistency_all_same_values(
        self,
        mock_format_consistency_result,
        mock_calculate_consistency_with_confidence,
        metric_consistency_instance,
    ):
        data = [5.0, 5.0, 5.0, 5.0, 5.0]
        mock_calculate_consistency_with_confidence.return_value = {
            "mean": 0.0,  # std of same values is 0
            "confidence_interval": (0.0, 0.0),
        }
        mock_format_consistency_result.return_value = ConsistencyResult(
            mean=1.0, confidence_interval=(1.0, 1.0)
        )

        result = metric_consistency_instance.calculate_consistency(data)

        mock_calculate_consistency_with_confidence.assert_called_once()
        mock_format_consistency_result.assert_called_once()
        args, kwargs = mock_format_consistency_result.call_args
        # max_score should be 1.0 when original max_score (max-min) is 0
        assert args[1] == 1.0
        assert result.mean == 1.0
        assert result.confidence_interval == (1.0, 1.0)
