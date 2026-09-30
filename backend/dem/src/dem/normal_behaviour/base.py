#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from abc import ABC, abstractmethod

# from collections.abc import Callable
from typing import Any, Sequence
import numpy as np


from dem.utils.logging_utils import setup_logger
from dem.normal_behaviour.utils import (
    NormalBehaviourResult,
    NormalBehaviourResultMetric,
    NormalBehaviourResultText,
)


logger = setup_logger(__name__)


class NormalBehaviour(ABC):
    def __init__(
        self,
        statistics: str,
    ):
        self.statistic = statistics
        #        self.statistic_function: Callable = None

    def _calculate_normal_behaviour_gaussian(
        self,
        sample: Sequence,
        k: float = 2.0,
    ) -> NormalBehaviourResult:
        """
        Defines normal behaviour as values within mean ± k·std (Gaussian assumption).
        Handles both 1D and 2D arrays. For 2D, computes per-feature statistics.
        Args:
            sample (Sequence): List or array of floats.
            k (float): Number of standard deviations for the normal range (default 2.0).
        Returns:
            NormalBehaviourResult: mean, std, lower, upper bounds for normal behaviour.
        """

        arr = np.asarray(sample, dtype=float)
        if arr.ndim == 1:
            mean = float(np.mean(arr)) if arr.size > 0 else float("nan")
            std = float(np.std(arr)) if arr.size > 0 else float("nan")
            lower = mean - k * std if arr.size > 0 else float("nan")
            upper = mean + k * std if arr.size > 0 else float("nan")

            return NormalBehaviourResultMetric(
                statistic=f"gaussian_mean±{k}std",
                centroid=mean,
                std=std,
                lower=lower,
                upper=upper,
            )
        elif arr.ndim == 2:
            mean = np.mean(arr, axis=0).tolist() if arr.size > 0 else []
            std = np.std(arr, axis=0).tolist() if arr.size > 0 else []
            lower = (
                (np.array(mean) - k * np.array(std)).tolist() if arr.size > 0 else []
            )
            upper = (
                (np.array(mean) + k * np.array(std)).tolist() if arr.size > 0 else []
            )

            return NormalBehaviourResultText(
                statistic=f"gaussian_mean±{k}std",
                centroid=mean,
                std=std,
                lower=lower,
                upper=upper,
            )
        else:
            raise ValueError("Input must be 1D or 2D array of floats")

    def _calculate_normal_behaviour_quantiles(
        self,
        sample: Sequence,
        lower_q: float = 0.05,
        upper_q: float = 0.95,
    ) -> NormalBehaviourResult:
        """
        Defines normal behaviour as values within [lower_q, upper_q] quantiles.
        Handles both 1D and 2D arrays. For 2D, computes per-feature quantiles.
        Args:
            sample (Sequence): List or array of floats.
            lower_q (float): Lower quantile (default 0.05 for 5th percentile).
            upper_q (float): Upper quantile (default 0.95 for 95th percentile).
        Returns:
            NormalBehaviourResult: lower and upper quantile bounds for normal behaviour.
        """
        arr = np.asarray(sample, dtype=float)
        if arr.ndim == 1:
            lower = float(np.quantile(arr, lower_q)) if arr.size > 0 else float("nan")
            upper = float(np.quantile(arr, upper_q)) if arr.size > 0 else float("nan")
            median = float(np.median(arr)) if arr.size > 0 else float("nan")

            return NormalBehaviourResultMetric(
                statistic=f"quantiles_{lower_q}_{upper_q}",
                lower=lower,
                upper=upper,
                centroid=median,
            )

        elif arr.ndim == 2:
            lower = np.quantile(arr, lower_q, axis=0).tolist() if arr.size > 0 else []
            upper = np.quantile(arr, upper_q, axis=0).tolist() if arr.size > 0 else []
            median = np.median(arr, axis=0).tolist() if arr.size > 0 else []

            return NormalBehaviourResultText(
                statistic=f"quantiles_{lower_q}_{upper_q}",
                lower=lower,
                upper=upper,
                centroid=median,
            )
        else:
            raise ValueError("Input must be 1D or 2D array of floats")

    def _calculate_normal_behaviour_by_var(
        self,
        sample: Sequence,
    ) -> NormalBehaviourResult:
        """
        Internal method to calculate normal behaviour for the provided data.

        Handles both 1D and 2D arrays. For 2D, computes per-feature statistics.

        Args:
            sample (Sequence): The input data for a calculation. The type will vary
                        based on the concrete implementation.

        Returns:
            NormalBehaviourResult: Dictionary with mean, std, and variance of the sample.
        """
        arr = np.asarray(sample, dtype=float)
        if arr.ndim == 1:
            mean = float(np.mean(arr)) if arr.size > 0 else float("nan")
            median = float(np.median(arr)) if arr.size > 0 else float("nan")
            std = float(np.std(arr)) if arr.size > 0 else float("nan")
            var = float(np.var(arr)) if arr.size > 0 else float("nan")
            upper = mean + std if arr.size > 0 else float("nan")
            lower = mean - std if arr.size > 0 else float("nan")

            return NormalBehaviourResultMetric(
                statistic=f"var_based_{self.statistic}",
                mean=mean,
                std=std,
                variance=var,
                centroid=mean,
                upper=upper,
                lower=lower,
                median=median,
            )
        elif arr.ndim == 2:
            mean = np.mean(arr, axis=0).tolist() if arr.size > 0 else []
            median = np.median(arr, axis=0).tolist() if arr.size > 0 else []
            std = np.std(arr, axis=0).tolist() if arr.size > 0 else []
            var = np.var(arr, axis=0).tolist() if arr.size > 0 else []
            upper = (np.array(mean) + np.array(std)).tolist() if arr.size > 0 else []
            lower = (np.array(mean) - np.array(std)).tolist() if arr.size > 0 else []

            return NormalBehaviourResultText(
                statistic=f"var_based_{self.statistic}",
                mean=mean,
                std=std,
                variance=var,
                centroid=mean,
                upper=upper,
                lower=lower,
                median=median,
            )
        else:
            raise ValueError("Input must be 1D or 2D array of floats")

    @abstractmethod
    def calculate_normal_behaviour(self, data: Any) -> NormalBehaviourResult:
        """
        Abstract method to calculate normal behaviour for the provided data.

        Concrete implementations must override this method to handle specific data types
        (e.g., List[float] for metrics, List[str] for text, networkx.Graph for graphs)
        and specific normal behaviour statistics.

        Args:
            data (Any): The input data for a calculation. The type will vary
                        based on the concrete implementation.

        Returns:
            NormalBehaviourResult: An object containing the normal behaviour calculation results,
                             including mean score, confidence interval, median, and indicator.
        """
