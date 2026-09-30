#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Sequence
import numpy as np

from .base import Consistency
from .utils import ConsistencyResult


class MetricConsistency(Consistency):
    """
    Calculates consistency for numerical metric data using statistical measures
    like standard deviation.

    This class extends the `Consistency` base class to provide specific
    implementations for calculating consistency scores and their confidence
    intervals for sequences of numerical values.
    """

    def __init__(
        self,
        statistic: str = "std",
        confidence_level: float = 95,
        sample_size: int = 10,
        N_nearest_neighbors: int = 100,
        N_bootstrap_samples: int = 2000,
    ):
        super().__init__(
            statistic,
            confidence_level,
            sample_size,
            N_nearest_neighbors,
            N_bootstrap_samples,
        )
        if self.statistic == "std":
            self.statistic_function = self._calculate_std_statistic
        else:
            raise ValueError(
                f"Unknown statistic: {self.statistic}. Only 'std' is supported."
            )

    def _calculate_std_statistic(
        self,
        sample: np.ndarray,
        bootstrap_samples,
    ) -> np.ndarray:
        """
        Calculates the standard deviation for each bootstrap sample.

        Args:
            sample (np.ndarray): The original sample (not directly used for std calculation here,
                                 but included for signature consistency with other statistic functions).
            bootstrap_samples: An iterable (array or generator) where each item is a bootstrap sample.

        Returns:
            np.ndarray: A 1D numpy array containing the standard deviation for each bootstrap sample.
        """
        std_values = []
        for bs_sample in bootstrap_samples:
            bs_array = np.asarray(bs_sample)
            if bs_array.size == 0:
                std_values.append(0.0)
                continue
            std_values.append(float(np.std(bs_array)))

        if not std_values:
            return np.array([0.0])
        return np.array(std_values)

    def calculate_consistency(
        self,
        data: Sequence[float],
    ) -> ConsistencyResult:
        """
        Calculates the consistency score for a given sequence of numerical data
        using bootstrap sampling methods.

        This function computes a statistic (e.g., standard deviation) of the metric
        values for neighboring data points and provides a confidence interval
        for this statistic using bootstrapping. The consistency score is then
        derived by transforming this statistic (e.g., `max_score - std`).

        Example: The consistency score can be derived from the standard deviation
        of scores of neighboring SessionIds. The confidence interval reflects the
        uncertainty in our estimation of that standard deviation.

        Args:
            data (Sequence[float]): The input numerical data (e.g., scores, metric values).
                                    This should represent the `N_nearest_neighbors` elements
                                    from which bootstrap samples will be drawn.
            statistic (str): The statistic used as a measure of consistency (e.g., "std" for standard deviation).
                             Currently, only "std" is implemented.

        Returns:
            ConsistencyResult: An object containing the consistency calculation results,
                               including mean score, confidence interval, and indicator.
        """

        if not data:
            # Return an empty/default result if no data is provided
            return ConsistencyResult()

        sample = np.asarray(data)

        # Compute consistency with confidence bounds
        consistency_with_conf = self._calculate_consistency_with_confidence(
            sample=sample
        )

        max_score = np.max(sample).item() - np.min(sample).item()
        # If all values are identical, std is 0, max_score for normalization should be 1 to avoid division by zero.
        if max_score == 0:
            max_score = 1.0  # This ensures normalization can proceed without errors, and consistency will be 1.0.

        return self._format_consistency_result(
            consistency_with_conf,
            max_score,
        )
