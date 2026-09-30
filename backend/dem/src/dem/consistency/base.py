#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Sequence, Tuple

import networkx as nx
import numpy as np

from .utils import ConsistencyResult


class Consistency(ABC):
    """
    Abstract Base Class for all consistency methods in the oxp library.

    This class provides common utilities for consistency calculations, including
    bootstrap sampling for confidence intervals and result formatting.
    """

    def __init__(
        self,
        statistic: str,
        confidence_level: float = 95,
        sample_size: int = 10,
        N_nearest_neighbors: int = 100,
        N_bootstrap_samples: int = 2000,
    ):
        """
        Initializer function for Consistency class.

        Args:
            confidence_level (float): The desired confidence level (e.g., 95 for 95%).
                                      Must be between 0 and 100.
            sample_size (int): The number of elements to include in each final bootstrap sample.
                               This is typically the number of nearest neighbors used for consistency calculation.
                               Must be at least 1.
            N_nearest_neighbors (int): The total number of elements available in the original sample
                                       from which bootstrap samples are drawn. Must be at least `sample_size`.
            N_bootstrap_samples (int): The total number of bootstrap samples to generate.
                                       Must be at least 1.

        Raises:
            ValueError: If any input parameter is out of its valid range.
        """
        if not statistic:
            raise ValueError("statitic function name is required.")
        if not (0 <= confidence_level <= 100):
            raise ValueError(
                f"confidence_level should be in [0,100], Received: {confidence_level}."
            )
        if sample_size < 1:
            raise ValueError(
                f"sample_size should be at least 1., Received: {sample_size}."
            )
        if N_nearest_neighbors < sample_size:
            raise ValueError(
                f"sample_size cannot exceed N_nearest_neighbors, Received: sample_size:{sample_size}, N_nearest_neighbors:{N_nearest_neighbors}."
            )
        if N_bootstrap_samples < 1:
            raise ValueError(
                f"N_bootstrap_samples should be at least 1., Received: {N_bootstrap_samples}."
            )

        self.statistic = statistic
        self.statistic_function: Callable = None

        self.confidence_level = confidence_level
        self.sample_size = sample_size
        self.N_nearest_neighbors = N_nearest_neighbors
        self.N_bootstrap_samples = N_bootstrap_samples

    def _generate_bootstrap_samples(
        self,
        sample: Sequence,
    ):
        """
        Generates N_bootstrap_samples bootstrap samples by sampling with replacement from an original sample.
        Yields samples one at a time to minimize memory footprint.

        Args:
            sample (np.ndarray): The original sample (e.g., metric values, or embeddings vectors).
                                 Can be a 1D array or an N-dimensional array where the first dimension
                                 represents the elements to be sampled.

        Yields:
            np.ndarray or list: Individual bootstrap samples of shape (sample_size, *sample.shape[1:])
                                or list of sampled elements for graph sequences.
        """

        is_graph_sequence = (
            isinstance(sample, list)
            and len(sample) > 0
            and isinstance(sample[0], (nx.Graph, nx.DiGraph))
        )
        if is_graph_sequence:
            # Do NOT convert to np.array, keep as list!
            pass
        else:
            sample = np.asarray(sample)

        # Ensure parameters are valid and sample is not empty
        N_original_sample_elements = len(sample)
        if (
            N_original_sample_elements == 0
            or self.N_bootstrap_samples <= 0
            or self.sample_size <= 0
        ):
            for _ in range(self.N_bootstrap_samples):
                yield np.zeros(
                    (self.sample_size, *sample.shape[1:]),
                    dtype=sample.dtype if hasattr(sample, "dtype") else float,
                )
            return

        # Generate bootstrap samples. Uniformly draw N_original_sample_elements elements with
        # replacement, then truncate the sample_size elements with smallest index
        resampled_count = np.random.multinomial(
            max(
                self.sample_size, N_original_sample_elements
            ),  # cover the case where N_original_sample_elements < sample_size
            pvals=[1 / N_original_sample_elements] * N_original_sample_elements,
            size=self.N_bootstrap_samples,
        )

        for i in range(self.N_bootstrap_samples):
            bootstrap_idx = np.repeat(
                np.arange(N_original_sample_elements), resampled_count[i]
            )[: self.sample_size]

            if is_graph_sequence:
                # Preserve graph objects
                yield [sample[int(idx)] for idx in bootstrap_idx]
            else:
                yield sample[bootstrap_idx]

    def _calculate_confidence_interval(
        self,
        results: np.ndarray,
    ) -> Tuple[float, float]:
        """
        Calculates the confidence interval (percentile-based) for a given array of statistics.

        Args:
            results (np.ndarray): A 1D numpy array of statistics (e.g., standard deviations from bootstrap samples).

        Returns:
            Tuple[float, float]: A tuple (lower_bound, upper_bound) representing the confidence interval.
        """
        q_left = (100 - self.confidence_level) / 2
        q_right = 100 - q_left
        return np.percentile(results, [q_left, q_right]).tolist()

    def _calculate_consistency_with_confidence(
        self,
        sample: Sequence,
    ) -> Dict[str, Any]:
        """
        Calculates the consistency score and its confidence interval using bootstrap sampling.

        This method generates multiple bootstrap samples from the original `sample`,
        applies a `statistic_function` to each bootstrap sample, and then computes
        the mean of these statistics along with a percentile-based confidence interval.

        Args:
            sample (Sequence): The original data sample from which bootstrap samples are drawn.

        Returns:
            Dict[str, Any]: A dictionary containing:
                            - "mean": The mean of the bootstrap statistics.
                            - "confidence_interval": A tuple (lower_bound, upper_bound)
                                                     for the statistic's confidence interval.
        """
        if not self.statistic_function:
            raise ValueError("Statistic function undefined for bootstrap sampling.")

        N_original_sample_elements = len(sample)
        if (
            N_original_sample_elements == 0
            or self.N_bootstrap_samples <= 0
            or self.sample_size <= 0
        ):
            return {
                "mean": np.nan,
                "confidence_interval": [np.nan, np.nan],
            }

        # Create multiple resampled versions of the sample data.
        bootstrap_samples = self._generate_bootstrap_samples(
            sample=sample,
        )

        # Apply the chosen statistic to each generated bootstrap sample.
        bootstrap_statistics = self.statistic_function(sample, bootstrap_samples)
        consistency = np.mean(bootstrap_statistics).item()

        # Determine the confidence interval for the statistic using percentiles of the bootstrap statistics.
        statistic_confidence_interval = self._calculate_confidence_interval(
            bootstrap_statistics,
        )

        return {
            "mean": consistency,
            "confidence_interval": statistic_confidence_interval,
        }

    def _format_consistency_result(
        self,
        consistency_with_conf: Dict,
        max_score: float,
        normalize: bool = True,
    ) -> ConsistencyResult:
        """
        Formats the raw consistency calculation results into a ConsistencyResult object.

        This method calculates the relative width of the confidence interval and
        determines a confidence indicator ("High", "Medium", "Low"). It also
        transforms the score from a "badness" metric (e.g., std dev, dispersion)
        to a "goodness" metric (consistency) by subtracting from `max_score`.
        Optionally normalizes the scores to a [0, 1] range.

        Args:
            consistency_with_conf (Dict): A dictionary containing "mean" and "confidence_interval"
                                          from `_calculate_consistency_with_confidence`.
            max_score (float): The maximum possible value for the raw statistic.
                               Used for transforming and normalizing scores.
            normalize (bool): If True, normalizes the scores and confidence interval
                              to a [0, 1] range based on `max_score`.

        Returns:
            ConsistencyResult: An object encapsulating the formatted consistency results.
        """
        # Handle the case where max_score is 0 and normalization is requested.
        # In this scenario, all scores should effectively be 0 after normalization.
        if normalize and max_score == 0:
            return ConsistencyResult.model_validate(
                {
                    "min": 0,
                    "max": 0,
                    "mean": 0,
                    "confidence_interval": (0, 0),
                    "confidence_indicator": "High",  # If max_score is 0, there's no variability, so high confidence.
                    "statistic": self.statistic,
                }
            )

        ci_width = (
            consistency_with_conf["confidence_interval"][1]
            - consistency_with_conf["confidence_interval"][0]
        )

        if (
            max_score == 0
        ):  # This should only happen if normalize is False, and the metric legitimately has a max of 0.
            relative_width = 0.0  # If max_score is 0, and ci_width is also 0, then relative width is 0.
        # If ci_width > 0 and max_score is 0, this indicates an issue with max_score definition.
        else:
            relative_width = ci_width / max_score

        if relative_width < 0.05:
            confidence_indicator = "High"
        elif 0.05 <= relative_width < 0.15:
            confidence_indicator = "Medium"
        else:
            confidence_indicator = "Low"

        # Transform from "badness" (e.g., std dev) to "goodness" (consistency)
        res = {
            "min": 0,
            "max": max_score,
            "mean": max_score - consistency_with_conf["mean"],
            "confidence_interval": [
                max_score - v
                for v in consistency_with_conf["confidence_interval"][
                    ::-1
                ]  # Reverse for consistency
            ],
            "confidence_indicator": confidence_indicator,
            "statistic": self.statistic,
        }

        if normalize and max_score > 0:
            # Only normalize if max_score is positive to avoid division by zero
            res["max"] = 1
            res["mean"] /= max_score
            res["confidence_interval"] = [
                r / max_score for r in res["confidence_interval"]
            ]

        return ConsistencyResult.model_validate(res)

    @abstractmethod
    def calculate_consistency(self, data: Any) -> ConsistencyResult:
        """
        Abstract method to calculate consistency for the provided data.

        Concrete implementations must override this method to handle specific data types
        (e.g., List[float] for metrics, List[str] for text, networkx.Graph for graphs)
        and specific consistency statistics.

        Args:
            data (Any): The input data for consistency calculation. The type will vary
                        based on the concrete implementation.

        Returns:
            ConsistencyResult: An object containing the consistency calculation results,
                               including mean score, confidence interval, and indicator.
        """
