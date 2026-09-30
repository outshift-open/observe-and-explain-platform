#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest
from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.utils._param_validation import InvalidParameterError

from dem.anomaly import AnomalyDetectionResult, MetricAnomalyDetector


def test_metric_anomaly_detector_init_default():
    """
    Tests that MetricAnomalyDetector initializes with default model (EllipticEnvelope)
    when no model_name is provided.
    """
    detector = MetricAnomalyDetector()
    assert detector.model_name == "elliptic_envelop"
    assert isinstance(detector.model, EllipticEnvelope)


def test_metric_anomaly_detector_init_valid_model_elliptic_envelop():
    """
    Tests initialization with 'elliptic_envelop' and custom kwargs.
    """
    detector = MetricAnomalyDetector(model_name="elliptic_envelop", contamination=0.15)
    assert detector.model_name == "elliptic_envelop"
    assert isinstance(detector.model, EllipticEnvelope)
    assert detector.model.contamination == 0.15


def test_metric_anomaly_detector_init_valid_model_isolation_forest():
    """
    Tests initialization with 'isolation_forest' and custom kwargs.
    """
    detector = MetricAnomalyDetector(
        model_name="isolation_forest", n_estimators=50, random_state=42
    )
    assert detector.model_name == "isolation_forest"
    assert isinstance(detector.model, IsolationForest)
    assert detector.model.n_estimators == 50
    assert detector.model.random_state == 42


def test_metric_anomaly_detector_init_invalid_model():
    """
    Tests that a ValueError is raised for an unknown model name.
    """
    with pytest.raises(ValueError, match="Unknown model name: invalid_model"):
        MetricAnomalyDetector(model_name="invalid_model")


# --- Test detect_outliers method ---


def test_detect_outliers_empty_list():
    """
    Tests detect_outliers with an empty list, expecting an empty AnomalyDetectionResult.
    """
    detector = MetricAnomalyDetector()
    result = detector.detect_outliers([])
    assert result == AnomalyDetectionResult()


def test_detect_outliers_elliptic_envelop_invalid_contamination():
    """
    Tests that EllipticEnvelope raises InvalidParameterError for contamination=0.0.
    """
    with pytest.raises(
        InvalidParameterError,
        match="The 'contamination' parameter of EllipticEnvelope must be a float in the range \\(0.0, 0.5\\]\\. Got 0.0 instead\\.",
    ):
        detector = MetricAnomalyDetector(
            model_name="elliptic_envelop", contamination=0.0
        )
        detector.detect_outliers([1.0, 1.1, 1.05, 0.95, 1.2, 0.9, 10.0, 11.0])


def test_detect_outliers_with_outliers_elliptic_envelop():
    """
    Tests EllipticEnvelope with data containing clear outliers.
    Contamination=0.25 for 8 samples means 2 outliers (8 * 0.25 = 2).
    """
    detector = MetricAnomalyDetector(model_name="elliptic_envelop", contamination=0.25)
    data = [1.0, 1.1, 1.05, 0.95, 1.2, 0.9, 10.0, 11.0]
    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) == 2
    assert sorted(result.outliers_values) == sorted([10.0, 11.0])
    assert len(result.inliers_indices) == 6


def test_detect_outliers_with_outliers_isolation_forest():
    """
    Tests IsolationForest with data containing clear outliers.
    Contamination=0.2 for 10 samples means 2 outliers (10 * 0.2 = 2).
    """
    detector = MetricAnomalyDetector(
        model_name="isolation_forest", contamination=0.2, random_state=42
    )
    data = [1.0, 1.1, 1.05, 0.95, 1.2, 0.9, 1.15, 0.85, 100.0, 101.0]
    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) == 2
    assert sorted(result.outliers_values) == sorted([100.0, 101.0])
    assert len(result.inliers_indices) == 8


def test_detect_outliers_all_same_value():
    """
    Tests that no outliers are detected when all metric values are identical.
    This relies on the `n_unique == 1` check in the detector.
    """
    detector = MetricAnomalyDetector()  # Uses default EllipticEnvelope
    data = [5.0, 5.0, 5.0, 5.0, 5.0]
    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) == 0
    assert len(result.inliers_indices) == len(data)
    assert sorted(result.inliers_values) == sorted(data)


def test_detect_outliers_single_value_list():
    """
    Tests anomaly detection with a list containing only one value.
    This should result in no outliers.
    """
    detector = MetricAnomalyDetector()
    data = [10.0]
    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) == 0
    assert len(result.inliers_indices) == 1
    assert result.inliers_values == [10.0]


def test_detect_outliers_two_values_one_outlier_isolation_forest():
    """
    Tests IsolationForest with a slightly larger dataset where one outlier is clear.
    IsolationForest struggles with only 2 samples.
    """
    detector = MetricAnomalyDetector(
        model_name="isolation_forest", contamination=0.2, random_state=42
    )
    data = [1.0, 1.1, 1.2, 100.0]  # 4 samples, expect 1 outlier
    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) == 1
    assert result.outliers_values == [100.0]
    assert len(result.inliers_indices) == 3
    assert sorted(result.inliers_values) == sorted([1.0, 1.1, 1.2])


def test_detect_outliers_two_values_one_outlier_elliptic_envelop():
    """
    Tests EllipticEnvelope with two values.
    EllipticEnvelope cannot estimate a real covariance matrix from just two
    points, so its degenerate-case handling classifies them either all as
    inliers or all as outliers -- which one is an sklearn implementation
    detail that has been observed to differ across platforms/BLAS backends
    (macOS vs Linux CI), not a behavior this codebase controls. Assert the
    detector runs without crashing and accounts for both points, without
    pinning the specific (platform-dependent) direction.
    """
    detector = MetricAnomalyDetector(model_name="elliptic_envelop", contamination=0.5)
    data = [1.0, 100.0]
    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) in (0, 2)
    assert len(result.outliers_indices) + len(result.inliers_indices) == 2
    assert sorted(result.outliers_values + result.inliers_values) == sorted(
        [1.0, 100.0]
    )


def test_detect_outliers_elliptic_envelope_sufficient_data_distinct_outlier():
    """
    Tests EllipticEnvelope with sufficient (Gaussian-like) data and a clear outlier.
    """
    detector = MetricAnomalyDetector(
        model_name="elliptic_envelop", contamination=0.125, random_state=42
    )  # Add random_state for reproducibility
    np.random.seed(42)  # Ensure reproducibility of random data
    inliers = list(np.random.normal(loc=0, scale=1, size=7))
    data = inliers + [100.0]

    result = detector.detect_outliers(data)
    assert len(result.outliers_indices) == 1
    assert result.outliers_values == [100.0]
    assert len(result.inliers_indices) == 7
    assert (
        100.0 not in result.inliers_values
    )  # Ensure the outlier isn't mistakenly in inliers


def test_detect_outliers_skips_invalid_values_keeps_original_indices():
    detector = MetricAnomalyDetector(model_name="isolation_forest", random_state=42)
    data = [1.0, None, np.nan, float("inf"), 1.1, "2.0"]

    result = detector.detect_outliers(data)

    # Only valid finite values are considered: indices 0, 4, 5
    assert sorted(result.inliers_indices + result.outliers_indices) == [0, 4, 5]
    assert 1 not in result.inliers_indices + result.outliers_indices
    assert 2 not in result.inliers_indices + result.outliers_indices
    assert 3 not in result.inliers_indices + result.outliers_indices


def test_detect_outliers_graceful_fallback_on_zero_sample_value_error(monkeypatch):
    detector = MetricAnomalyDetector(model_name="elliptic_envelop")
    monkeypatch.setattr(
        detector.model,
        "fit_predict",
        lambda _: (_ for _ in ()).throw(
            ValueError(
                "Found array with 0 sample(s) (shape=(0, 1)) while a minimum of 1 is required."
            )
        ),
    )

    data = [1.0, 1.1, 1.2, 1.3]
    result = detector.detect_outliers(data)

    assert result.outliers_indices == []
    assert sorted(result.inliers_indices) == [0, 1, 2, 3]
    assert sorted(result.inliers_values) == sorted(data)
