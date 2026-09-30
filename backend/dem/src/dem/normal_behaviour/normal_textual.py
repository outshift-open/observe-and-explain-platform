#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Sequence
import numpy as np
from sklearn.neighbors import KernelDensity
from scipy.stats import chi2

from dem.normal_behaviour.base import NormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourResultText


class TextNormalBehaviour(NormalBehaviour):
    def __init__(
        self,
        statistic: str,
    ):
        super().__init__(statistic)

    def calculate_normal_behaviour(
        self,
        data: Sequence[Sequence[float]],
        raw_samples: Sequence[
            str
        ] = None,  # original text data corresponding to the embeddings, used for representative point selection
    ) -> NormalBehaviourResultText:
        if not data:
            # Return an empty/default result if no data is provided
            return NormalBehaviourResultText()

        embeddings = np.asarray(data)

        if embeddings.size == 0:
            return NormalBehaviourResultText()

        if self.statistic == "gaussian":
            result_data = self._calculate_normal_behaviour_gaussian(embeddings)
        elif self.statistic == "quantiles":
            result_data = self._calculate_normal_behaviour_quantiles(embeddings)
        elif self.statistic == "var_based":
            result_data = self._calculate_normal_behaviour_by_var(embeddings)
        elif self.statistic == "centroid":
            result_data = self._calculate_centroid(embeddings)
        elif self.statistic == "density":
            result_data = self._calculate_density_based(embeddings)
        elif self.statistic == "ellipse":
            result_data = self._calculate_confidence_ellipse(embeddings)
        else:
            raise ValueError(f"Unknown statistic: {self.statistic}")

        representative_point_index = self._find_closest(
            result_data.centroid, embeddings
        )
        if raw_samples is not None:
            result_data.representative_processed_sample = raw_samples[
                representative_point_index
            ]

        result_data.representative_sample = embeddings[
            representative_point_index
        ].tolist()
        result_data.statistic = self.statistic
        return result_data

    def _calculate_centroid(self, embeddings):
        centroid = np.mean(embeddings, axis=0)

        return NormalBehaviourResultText(
            statistic="centroid",
            centroid=centroid.tolist() if centroid.ndim > 0 else float(centroid),
        )

    def _calculate_density_based(self, embeddings, quantile=0.95):
        # Uses kernel density estimation to define a density threshold for normality
        kde = KernelDensity(kernel="gaussian", bandwidth=1.0).fit(embeddings)
        log_dens = kde.score_samples(embeddings)
        threshold = np.quantile(log_dens, 1 - quantile)

        centroid = np.mean(embeddings, axis=0)

        return NormalBehaviourResultText(
            statistic=f"density_kde_{quantile}",
            centroid=centroid.tolist(),
            other_info={"density_threshold": threshold},
        )

    def _calculate_confidence_ellipse(self, embeddings, confidence_level=0.95):
        """
        Generalized confidence ellipsoid for N dimensions using Mahalanobis distance.
        Returns centroid, covariance, and chi2 threshold for the ellipsoid.
        """
        mean = np.mean(embeddings, axis=0)
        cov = np.cov(embeddings, rowvar=False)
        n_dim = embeddings.shape[1]
        # Mahalanobis threshold for the ellipsoid
        threshold = chi2.ppf(confidence_level, df=n_dim)
        # For 2D, also return width/height/angle for backward compatibility
        ellipse_info = {}
        if n_dim == 2:
            vals, vecs = np.linalg.eigh(cov)
            order = vals.argsort()[::-1]
            vals, vecs = vals[order], vecs[:, order]
            width, height = 2 * np.sqrt(vals * threshold)
            angle = np.degrees(np.arctan2(*vecs[:, 0][::-1]))
            ellipse_info = dict(upper=width, lower=height, angle=float(angle))

        return NormalBehaviourResultText(
            statistic=f"confidence_ellipsoid_{confidence_level}",
            centroid=mean.tolist(),
            covariance=cov.tolist(),
            mahalanobis_threshold=float(threshold),
            **ellipse_info,
        )

    def _find_closest(
        self, sample: np.ndarray, data: np.ndarray
    ) -> int:  # index of closest point in data to sample
        # Helper function to find the index of the closest point in data to the sample
        distances = np.linalg.norm(data - sample, axis=1)
        return np.argmin(distances)
