#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Sequence
import numpy as np

from .base import Consistency
from .utils import ConsistencyResult
from ..grouping import SemanticGrouper


class TextualConsistency(Consistency):
    """
    Calculates consistency for textual data, typically represented as embeddings,
    using measures like directional dispersion or semantic entropy.

    This class extends the `Consistency` base class to provide specific
    implementations for calculating consistency scores and their confidence
    intervals for sequences of text embeddings.
    """

    def __init__(
        self,
        statistic: str = "dispersion",
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
        if self.statistic == "dispersion":
            self.statistic_function = self._calculate_directional_dispersion
        elif self.statistic == "entropy":
            self.statistic_function = self._calculate_semantic_entropy
        else:
            raise ValueError(
                f"Unknown statistic: {self.statistic}. Only 'dispersion' or 'entropy' are supported."
            )

    def _calculate_directional_dispersion(
        self,
        sample: np.ndarray,
        bootstrap_samples,
    ) -> np.ndarray:
        """
        Computes a measure of directional dispersion (analogous to variance)
        for a set of N-dimensional vectors, based on cosine distance.

        This method normalizes vectors to unit length and then calculates
        1 minus the magnitude of their mean resultant vector.
        It operates on each bootstrap sample individually.

        Args:
            sample (np.ndarray): The original sample of embeddings (not directly used here,
                                 but included for signature consistency).
            bootstrap_samples: An iterable (array or generator) yielding bootstrap samples,
                               each containing N-dimensional vectors (embeddings).
                               Each sample has shape (sample_size, embedding_dim).

        Returns:
            np.ndarray: A 1D numpy array containing a measure of dispersion (0 to 1)
                        for each bootstrap sample.
                        0 indicates perfectly aligned vectors (minimum dispersion).
                        1 indicates highly dispersed vectors (maximum dispersion).
                        Returns 0.0 if a bootstrap sample is empty or contains only zero vectors.
        """
        dispersions = []
        for bs_sample in bootstrap_samples:
            if len(bs_sample) == 0:
                dispersions.append(0.0)
                continue

            bs_array = np.asarray(bs_sample)
            # Handle cases where all vectors in the sample are zero vectors
            # np.linalg.norm will return 0 for zero vectors, leading to division by zero (NaN)
            # and then a dispersion of 1.0 (1 - 0) if not handled.
            if np.all(bs_array == 0):
                dispersions.append(0.0)
                continue

            # Normalize vectors to unit length
            norm_bs_sample = bs_array / np.linalg.norm(bs_array, axis=1, keepdims=True)
            # Handle NaN values that might arise from division by zero for individual zero vectors
            # (e.g., if some vectors were zero, but not all). Replace NaN with 0.
            norm_bs_sample[np.isnan(norm_bs_sample)] = 0

            mean_resultant_vector = np.sum(norm_bs_sample, axis=0) / bs_array.shape[0]

            r_bar = np.linalg.norm(mean_resultant_vector)
            r_bar = np.clip(r_bar, 0.0, 1.0)  # Ensure r_bar is within [0, 1]
            dispersion = 1 - r_bar
            dispersions.append(dispersion)

        return np.array(dispersions)

    def _calculate_semantic_entropy(
        self,
        sample: np.ndarray,
        bootstrap_samples,
    ) -> np.ndarray:
        """
        Computes a measure of semantic entropy for a set of N-dimensional
        vectors. This method clusters the replies based on their semantic
        meaning, and computes a value of entropy on these equivalence classes.

        Args:
            sample (np.ndarray): The original sample of embeddings.
            bootstrap_samples: An iterable (array or generator) yielding bootstrap samples.

        Returns:
            np.ndarray: A 1D numpy array of entropy values for each bootstrap sample.
                Returns 0.0 if the input is empty or contains only zero vectors.
        """
        # Ensure embeddings is array
        original_sample = np.asarray(sample)

        if original_sample.size == 0:
            return np.array([0.0] * self.N_bootstrap_samples)

        # Retrieve semantic equivalence classes by running clustering algorithm
        # from the ListGroups endpoint
        sc = SemanticGrouper()
        equivalence_classes = sc.cluster_embeddings_with_radius(
            dict(
                zip(
                    [str(r) for r in range(len(original_sample))],
                    original_sample,
                )
            )
        )

        # Create a mapping of sample to class to simplify computation
        classes = {}
        i = 0
        if len(equivalence_classes) > 0:
            for eq_class in equivalence_classes:
                for session_id in eq_class["session_ids"]:
                    classes[original_sample[int(session_id)].tobytes()] = i
                    if eq_class["group_id"] == "Unassigned":
                        i += 1
                i += 1

        entropies_list = []

        # Compute entropy for each bootstrap sample (consuming generator one at a time)
        for bs_sample in bootstrap_samples:
            bs_array = np.asarray(bs_sample)
            N_total_embeddings = bs_array.shape[0]
            # Retrieve and count classes of bootstrap sample
            sample_classes = np.asarray([classes[s.tobytes()] for s in bs_array])
            counts_bincount = np.bincount(sample_classes)

            # Compute entropy
            entropy = 0
            for count in counts_bincount:
                if count > 0:
                    entropy -= (count / N_total_embeddings) * np.log(
                        count / N_total_embeddings
                    )
            entropies_list.append(entropy)

        return np.array(entropies_list)

    def calculate_consistency(
        self,
        data: Sequence[Sequence[float]],
    ) -> ConsistencyResult:
        """
        Calculates the consistency score for a given sequence of text embeddings
        using bootstrap sampling methods.

        This function computes a statistic (e.g., directional dispersion or semantic entropy)
        of the embeddings for neighboring data points and provides a confidence interval
        for this statistic using bootstrapping. The consistency score is then
        derived by transforming this statistic (e.g., `max_score - dispersion`).

        Args:
            data (Sequence[Sequence[float]]): The input textual data, expected as a sequence
                                              of numerical embeddings (e.g., `List[List[float]]`).
                                              This should represent the `N_nearest_neighbors` elements
                                              from which bootstrap samples will be drawn.
            statistic (str): The statistic used as a measure of consistency (e.g., "dispersion", "entropy").

        Returns:
            ConsistencyResult: An object containing the consistency calculation results,
                               including mean score, confidence interval, and indicator.
        """

        embeddings = np.asarray(data)

        if embeddings.size == 0:
            return ConsistencyResult()

        # Compute consistency with confidence bounds
        consistency_with_conf = self._calculate_consistency_with_confidence(
            sample=embeddings,
        )

        # Determine max_score based on the statistic for transformation and normalization
        if self.statistic == "dispersion":
            # Directional dispersion ranges from 0 to 1. Max score is 1.0.
            max_score = 1.0
        elif self.statistic == "entropy":
            # Max entropy for N items is log(N). Here, N is sample_size for bootstrap samples.
            max_score = np.log(self.sample_size) if self.sample_size > 0 else 0.0
        else:
            # Fallback for unknown statistic, though validation should prevent this
            max_score = 1.0

        return self._format_consistency_result(
            consistency_with_conf, max_score, self.statistic
        )
