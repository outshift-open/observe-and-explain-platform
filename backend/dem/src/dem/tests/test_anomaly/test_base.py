#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
from typing import Any

from dem.anomaly import AnomalyDetector, AnomalyDetectionResult


def test_anomaly_detector_cannot_be_instantiated():
    """
    Tests that the abstract AnomalyDetector class cannot be instantiated directly.
    """
    with pytest.raises(
        TypeError,
        match="Can't instantiate abstract class AnomalyDetector without an implementation for abstract method 'detect_outliers'",
    ):
        AnomalyDetector()


def test_concrete_detector_must_implement_abstract_method():
    """
    Tests that a concrete class inheriting from AnomalyDetector must implement
    the 'detect_outliers' method.
    """

    class IncompleteDetector(AnomalyDetector):
        # Missing detect_outliers implementation
        pass

    with pytest.raises(
        TypeError,
        match="Can't instantiate abstract class IncompleteDetector without an implementation for abstract method 'detect_outliers'",
    ):
        IncompleteDetector()


def test_concrete_detector_implements_abstract_method_correctly():
    """
    Tests that a concrete class implementing AnomalyDetector can be instantiated
    and its detect_outliers method can be called.
    """

    class MockConcreteDetector(AnomalyDetector):
        def detect_outliers(self, data: Any) -> AnomalyDetectionResult:
            # Simulate some detection logic
            if data == [1, 2, 3, 100]:
                return AnomalyDetectionResult(
                    inliers_indices=[0, 1, 2],
                    inliers_values=[1.0, 2.0, 3.0],
                    outliers_indices=[3],
                    outliers_values=[100.0],
                )
            return AnomalyDetectionResult()

    detector = MockConcreteDetector()
    assert isinstance(detector, AnomalyDetector)

    # Test calling the implemented method
    result = detector.detect_outliers([1, 2, 3, 100])
    assert len(result.outliers_indices) == 1
    assert result.outliers_values == [100.0]
    assert len(result.inliers_indices) == 3
    assert result.inliers_values == [1.0, 2.0, 3.0]

    result_empty = detector.detect_outliers([])
    assert result_empty == AnomalyDetectionResult()
