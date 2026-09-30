#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Sequence

import numpy as np

from .base import AnomalyDetector
from .utils import AnomalyDetectionResult
from ..utils import setup_logger

logger = setup_logger(__name__)


class TextualAnomalyDetector(AnomalyDetector):
    """
    Anomaly detector for textual data.
    """

    def __init__(self, model_name=None, **kwargs):
        super().__init__(model_name, **kwargs)

    def detect_outliers(
        self, embeddings: Sequence[Sequence[float]]
    ) -> AnomalyDetectionResult:
        """
        Detects outliers in a list of embedding vectors.

        Args:
            embeddings (Sequence[Sequence[float]]): A list of embedding vectors to analyze.
                                                    Each inner sequence represents a single embedding.

        Returns:
            AnomalyDetectionResult: An object containing the detection results,
                                    including indices and values of inliers and outliers.
        """
        embeddings_np = np.asarray(embeddings)

        if embeddings_np.size == 0:
            logger.warning(
                "No embeddings provided for anomaly detection. Returning empty result."
            )
            return AnomalyDetectionResult()

        if len(embeddings_np) < 2:
            return AnomalyDetectionResult(
                inliers_indices=[0] if embeddings else [],
                inliers_values=embeddings if embeddings else [],
            )

        if len(np.unique(embeddings_np, axis=0)) == 1:
            logger.info("All embeddings are identical. Assuming no outliers.")
            y_pred = np.ones(len(embeddings_np))  # All points are inliers.
        else:
            try:
                y_pred = self.model.fit_predict(embeddings_np)
            except ValueError as e:
                if "The covariance matrix of the support data is equal to 0" in str(e):
                    logger.warning(
                        f"Degenerate data for {self.model_name}. Assuming no outliers. Error: {e}"
                    )
                    y_pred = np.ones(len(embeddings_np))  # All points are inliers.
                else:
                    raise

        inliers_indices = [i for i, prediction in enumerate(y_pred) if prediction == 1]
        outliers_indices = [
            i for i, prediction in enumerate(y_pred) if prediction == -1
        ]

        inliers_values = [embeddings[i] for i in inliers_indices]
        outliers_values = [embeddings[i] for i in outliers_indices]

        return AnomalyDetectionResult(
            inliers_indices=inliers_indices,
            inliers_values=inliers_values,
            outliers_indices=outliers_indices,
            outliers_values=outliers_values,
        )
