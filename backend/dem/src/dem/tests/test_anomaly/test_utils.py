#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from dem.anomaly import AnomalyDetectionResult


def test_anomaly_detection_result_default_init():
    """
    Tests that AnomalyDetectionResult initializes with default empty lists and None threshold.
    """
    result = AnomalyDetectionResult()
    assert result.inliers_indices == []
    assert result.inliers_values == []
    assert result.outliers_indices == []
    assert result.outliers_values == []
    assert result.scores == []
    assert result.threshold is None


def test_anomaly_detection_result_custom_init():
    """
    Tests that AnomalyDetectionResult initializes correctly with custom provided values.
    """
    in_indices = [0, 2]
    in_values = [1.0, 3.0]
    out_indices = [1]
    out_values = [10.0]
    scores = [0.1, 0.9, 0.2]
    threshold = 0.5

    result = AnomalyDetectionResult(
        inliers_indices=in_indices,
        inliers_values=in_values,
        outliers_indices=out_indices,
        outliers_values=out_values,
        scores=scores,
        threshold=threshold,
    )

    assert result.inliers_indices == in_indices
    assert result.inliers_values == in_values
    assert result.outliers_indices == out_indices
    assert result.outliers_values == out_values
    assert result.scores == scores
    assert result.threshold == threshold


def test_anomaly_detection_result_partial_init():
    """
    Tests that AnomalyDetectionResult handles partial initialization correctly,
    filling missing fields with defaults.
    """
    in_indices = [0]
    in_values = [5.0]

    result = AnomalyDetectionResult(
        inliers_indices=in_indices, inliers_values=in_values
    )

    assert result.inliers_indices == in_indices
    assert result.inliers_values == in_values
    assert result.outliers_indices == []
    assert result.outliers_values == []
    assert result.scores == []
    assert result.threshold is None


def test_anomaly_detection_result_threshold_can_be_none():
    """
    Tests that the threshold can explicitly be set to None.
    """
    result = AnomalyDetectionResult(threshold=None)
    assert result.threshold is None
