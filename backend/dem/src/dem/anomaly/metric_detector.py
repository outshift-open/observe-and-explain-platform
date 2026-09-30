#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import List

import numpy as np

from ..utils import setup_logger
from .base import AnomalyDetector
from .utils import AnomalyDetectionResult

logger = setup_logger(__name__)


class MetricAnomalyDetector(AnomalyDetector):
    """
    Anomaly detector for numerical metric values.
    """

    def __init__(self, model_name="elliptic_envelop", **kwargs):
        super().__init__(model_name, **kwargs)

    def detect_outliers(self, metric_values: List[float]) -> AnomalyDetectionResult:
        """
        Detects outliers in a list of numerical metric values.

        Args:
            metric_values (List[float]): A list of numerical values to analyze.

        Returns:
            AnomalyDetectionResult: An object containing the detection results.
        """
        if not metric_values:
            logger.warning(
                "No metric values provided for anomaly detection. Returning empty result."
            )
            return AnomalyDetectionResult()

        # Keep only finite numeric values and preserve mapping to original positions.
        valid_indices = []
        valid_values = []
        for i, value in enumerate(metric_values):
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                logger.debug(
                    "Skipping non-numeric metric value at index %s: %r", i, value
                )
                continue

            if np.isfinite(numeric_value):
                valid_indices.append(i)
                valid_values.append(numeric_value)
            else:
                logger.debug(
                    "Skipping non-finite metric value at index %s: %r", i, value
                )

        if not valid_values:
            logger.warning(
                "No valid finite metric values provided for anomaly detection. Returning empty result."
            )
            return AnomalyDetectionResult()

        # Sklearn models typically expect 2D arrays (n_samples, n_features)
        metric_values_np = np.asarray(valid_values, dtype=float).reshape(-1, 1)

        # Handle cases with all unique values or very few samples
        if len(metric_values_np) < 2:  # Cannot detect outliers with less than 2 samples
            return AnomalyDetectionResult(
                inliers_indices=valid_indices,
                inliers_values=[metric_values[i] for i in valid_indices],
            )

        n_unique = len(np.unique(metric_values_np))
        if n_unique == 1:  # All values equal implies no outliers
            y_pred = np.ones(len(metric_values_np))
        else:
            try:
                y_pred = self.model.fit_predict(metric_values_np)
            except ValueError as e:
                # Specific handling for EllipticEnvelope covariance matrix error
                if "The covariance matrix of the support data is equal to 0" in str(
                    e
                ) or "Found array with 0 sample(s)" in str(e):
                    logger.warning(
                        "Model %s failed on metric series (%s). Falling back to all inliers. Error: %s",
                        self.model_name,
                        len(valid_values),
                        e,
                    )
                    y_pred = np.ones(len(metric_values_np))
                else:
                    raise

        inliers_positions = [
            i for i, prediction in enumerate(y_pred) if prediction == 1
        ]
        inliers_indices = [valid_indices[i] for i in inliers_positions]
        outliers_indices = [
            valid_indices[i] for i, prediction in enumerate(y_pred) if prediction == -1
        ]

        inliers_values = [metric_values[i] for i in inliers_indices]
        outliers_values = [metric_values[i] for i in outliers_indices]

        return AnomalyDetectionResult(
            inliers_indices=inliers_indices,
            inliers_values=inliers_values,
            outliers_indices=outliers_indices,
            outliers_values=outliers_values,
        )
