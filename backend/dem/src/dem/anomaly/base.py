#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from typing import Any

from sklearn.covariance import EllipticEnvelope
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor

from .utils import AnomalyDetectionResult


class AnomalyDetector(ABC):
    """
    Abstract Base Class for all anomaly detectors in the oxp library.
    Defines the common interface for detecting anomalies across different data types.
    """

    def __init__(self, model_name: str = None, **kwargs):
        self._models = {
            # Elliptic Envelope uses ROBUST covariant estimates and assumes the inliers are
            # distributed according to a Gaussian (hence, the data is assumed to have a single mode!).
            # support_fraction denotes the fraction of samples to estimate the non-polluted covariance,
            # its default (None) is (n_samples + n_features + 1)/(2 * n_samples).
            # contamination denotes the fraction of samples that are expected to be outliers.
            # WARNING: not expected to yield meaningful results when n_samples > (n_features)^2 !
            # EllipticEnvelope(support_fraction=None, contamination=0.1)
            "elliptic_envelop": EllipticEnvelope,
            # Isolation Forest with its default sklearn parameters set explicitly.
            # Here, max_samples="auto", means max_samples=min(256,n_samples), as suggested by the
            # original paper.
            # Further, contamination="auto" means that the offset=-0.5 is used to classify points.
            # Putting it to a fraction, e.g., 0.1=10%, means that the offset will be calibrated such
            # that 10% of the points are classified as outliers.
            # IsolationForest(n_estimators=100, max_samples="auto", contamination="auto")
            "isolation_forest": IsolationForest,
            # Local Outlier Factor, note that n_neighbours is difficult to estimate from the data,
            # according to literature, its default value can be put at 20.
            # LocalOutlierFactor(n_neighbors=20, contamination=0.1)
            "local_outlier_factor": LocalOutlierFactor,
        }
        if model_name is None:
            self.model_name = "isolation_forest"
        else:
            self.model_name = model_name

        if self.model_name not in self._models:
            raise ValueError(
                f"Unknown model name: {self.model_name}. Choose from {list(self._models.keys())}"
            )
        self.model = self._models[self.model_name](**kwargs)

    @abstractmethod
    def detect_outliers(self, data: Any) -> AnomalyDetectionResult:
        """
        Abstract method to detect outliers in the provided data.
        Concrete implementations must override this method to handle specific data types
        (e.g., List[float] for metrics, List[str] for text, networkx.Graph for graphs).

        Args:
            data: The input data for anomaly detection. The type will vary based on the detector.

        Returns:
            AnomalyDetectionResult: An object containing the detection results,
                                    including anomaly flags, scores, and threshold.
        """
