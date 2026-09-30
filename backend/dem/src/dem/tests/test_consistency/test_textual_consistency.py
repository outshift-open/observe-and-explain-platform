#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch

import numpy as np
import pytest

from dem.consistency import ConsistencyResult, TextualConsistency


@pytest.fixture
def textual_consistency_instance():
    return TextualConsistency(
        confidence_level=95,
        sample_size=5,
        N_nearest_neighbors=10,
        N_bootstrap_samples=100,
    )


class TestTextualConsistency:
    def test_initialization(self, textual_consistency_instance):
        assert isinstance(textual_consistency_instance, TextualConsistency)
        assert textual_consistency_instance.confidence_level == 95

    @pytest.mark.parametrize(
        "bootstrap_samples, expected_dispersions",
        [
            # Perfectly aligned vectors
            (np.array([[[1, 0], [1, 0], [1, 0]]], dtype=np.float64), np.array([0.0])),
            # Highly dispersed vectors (orthogonal)
            (
                np.array([[[1, 0], [0, 1], [-1, 0]]], dtype=np.float64),
                np.array([1 - (1 / 3)]),
            ),  # Mean resultant vector will be (0, 1/3)
            # Mixed vectors
            (
                np.array([[[1, 0], [1, 0], [0, 1]]], dtype=np.float64),
                np.array([1 - np.linalg.norm(np.array([2 / 3, 1 / 3]))]),
            ),
            # Zero vectors - EXPECT 0.0
            (np.array([[[0, 0], [0, 0]]], dtype=np.float64), np.array([0.0])),
            # Empty bootstrap sample - ensure consistent embedding_dim for reshape
            (np.array([[]]).reshape(1, 0, 2), np.array([0.0])),
            # Multiple bootstrap samples
            (
                np.array([[[1, 0], [1, 0]], [[1, 0], [0, 1]]], dtype=np.float64),
                np.array([0.0, 1 - np.linalg.norm(np.array([0.5, 0.5]))]),
            ),
        ],
    )
    def test_calculate_directional_dispersion(
        self, textual_consistency_instance, bootstrap_samples, expected_dispersions
    ):
        sample = np.array([])  # Not used by this method
        dispersions = textual_consistency_instance._calculate_directional_dispersion(
            sample, bootstrap_samples
        )
        assert isinstance(dispersions, np.ndarray)
        assert np.allclose(dispersions, expected_dispersions)
        assert np.all((dispersions >= 0) & (dispersions <= 1))

    @patch("dem.consistency.textual_consistency.SemanticGrouper")
    def test_calculate_semantic_entropy_basic(
        self, MockSemanticGrouper, textual_consistency_instance
    ):
        # Mock SemanticGrouper and its clustering method
        mock_grouper_instance = MockSemanticGrouper.return_value
        # Modified mock to include an "Unassigned" group, as per actual SemanticGrouper behavior
        mock_grouper_instance.cluster_embeddings_with_radius.return_value = [
            {
                "group_id": "GroupA",
                "session_ids": ["0", "1"],
            },
            {"group_id": "GroupB", "session_ids": ["2"]},
            {"group_id": "Unassigned", "session_ids": ["3"]},
        ]

        sample_embeddings = np.array(
            [[1.0, 1.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], dtype=np.float64
        )  # original sample
        # Bootstrap samples where elements map to the mocked classes
        bootstrap_samples = np.array(
            [
                [sample_embeddings[0], sample_embeddings[1], sample_embeddings[2]],
                [sample_embeddings[0], sample_embeddings[0], sample_embeddings[0]],
            ],
            dtype=np.float64,
        )
        textual_consistency_instance.N_bootstrap_samples = 2
        textual_consistency_instance.sample_size = 3

        entropies = textual_consistency_instance._calculate_semantic_entropy(
            sample=sample_embeddings, bootstrap_samples=bootstrap_samples
        )

        assert isinstance(entropies, np.ndarray)
        assert entropies.shape == (2,)

        # Expected entropy for first bootstrap sample: pA=2/3, pB=1/3
        # - (2/3 * log(2/3) + 1/3 * log(1/3))
        expected_entropy_1 = -((2 / 3) * np.log(2 / 3) + (1 / 3) * np.log(1 / 3))
        assert np.isclose(entropies[0], expected_entropy_1)

        # Expected entropy for second bootstrap sample: pA=3/3 = 1
        # - (1 * log(1)) = 0
        expected_entropy_2 = 0.0
        assert np.isclose(entropies[1], expected_entropy_2)

        MockSemanticGrouper.assert_called_once()
        mock_grouper_instance.cluster_embeddings_with_radius.assert_called_once()

    @patch("dem.consistency.textual_consistency.SemanticGrouper")
    def test_calculate_semantic_entropy_empty_samples(
        self, MockSemanticGrouper, textual_consistency_instance
    ):
        sample_embeddings = np.array([])
        bootstrap_samples = np.array([[]]).reshape(0, 0, 2)
        textual_consistency_instance.N_bootstrap_samples = 5
        textual_consistency_instance.sample_size = 0

        entropies = textual_consistency_instance._calculate_semantic_entropy(
            sample=sample_embeddings, bootstrap_samples=bootstrap_samples
        )
        assert isinstance(entropies, np.ndarray)
        assert entropies.shape == (textual_consistency_instance.N_bootstrap_samples,)
        assert np.allclose(entropies, 0.0)
        MockSemanticGrouper.assert_not_called()

    @patch("dem.consistency.textual_consistency.SemanticGrouper")
    def test_calculate_semantic_entropy_unassigned_groups(
        self, MockSemanticGrouper, textual_consistency_instance
    ):
        mock_grouper_instance = MockSemanticGrouper.return_value
        mock_grouper_instance.cluster_embeddings_with_radius.return_value = [
            {
                "group_id": "Unassigned",
                "session_ids": ["0", "1"],
            },  # Each gets unique ID
            {"group_id": "GroupB", "session_ids": ["2", "3"]},  # Share ID
        ]

        sample_embeddings = np.array(
            [[1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [4.0, 4.0]], dtype=np.float64
        )
        bootstrap_samples = np.array(
            [
                [
                    sample_embeddings[0],
                    sample_embeddings[1],
                    sample_embeddings[2],
                ],  # Maps to C0, C1, C2
            ],
            dtype=np.float64,
        )
        textual_consistency_instance.N_bootstrap_samples = 1
        textual_consistency_instance.sample_size = 3

        entropies = textual_consistency_instance._calculate_semantic_entropy(
            sample=sample_embeddings, bootstrap_samples=bootstrap_samples
        )

        # Expected: 3 unique classes for 3 items. p=1/3 for each.
        # original_sample[0] (class 0), original_sample[1] (class 1), original_sample[2] (class 2)
        # Entropy = -3 * (1/3 * log(1/3)) = -log(1/3) = log(3)
        expected_entropy = np.log(3)
        assert np.isclose(entropies[0], expected_entropy)

    @patch.object(TextualConsistency, "_calculate_consistency_with_confidence")
    @patch.object(TextualConsistency, "_format_consistency_result")
    def test_calculate_consistency_dispersion(
        self,
        mock_format_consistency_result,
        mock_calculate_consistency_with_confidence,
        textual_consistency_instance,
    ):
        data = [[1.0, 0.0], [0.9, 0.1], [1.0, 0.0]]  # Changed to float literals
        mock_calculate_consistency_with_confidence.return_value = {
            "mean": 0.1,
            "confidence_interval": (0.05, 0.15),
        }
        mock_format_consistency_result.return_value = ConsistencyResult(
            mean=0.9, confidence_interval=(0.85, 0.95)
        )

        result = textual_consistency_instance.calculate_consistency(data)

        mock_calculate_consistency_with_confidence.assert_called_once()
        _args, kwargs = mock_calculate_consistency_with_confidence.call_args
        assert np.array_equal(kwargs["sample"], np.asarray(data))

        mock_format_consistency_result.assert_called_once()
        args, kwargs = mock_format_consistency_result.call_args
        assert args[0] == {"mean": 0.1, "confidence_interval": (0.05, 0.15)}
        assert args[1] == 1.0  # max_score for dispersion is 1.0
        assert args[2] == "dispersion"

        assert isinstance(result, ConsistencyResult)
        assert result.mean == 0.9

    @patch("dem.consistency.textual_consistency.SemanticGrouper")
    @patch.object(TextualConsistency, "_calculate_consistency_with_confidence")
    @patch.object(TextualConsistency, "_format_consistency_result")
    def test_calculate_consistency_entropy(
        self,
        mock_format_consistency_result,
        mock_calculate_consistency_with_confidence,
        MockSemanticGrouper,
    ):
        textual_consistency_instance = TextualConsistency(statistic="entropy")
        data = [[1.0, 1.0], [1.0, 1.0], [2.0, 2.0]]  # Changed to float literals
        textual_consistency_instance.sample_size = 3
        mock_calculate_consistency_with_confidence.return_value = {
            "mean": 0.5,
            "confidence_interval": (0.4, 0.6),
        }
        mock_format_consistency_result.return_value = ConsistencyResult(
            mean=0.7, confidence_interval=(0.6, 0.8)
        )
        MockSemanticGrouper.return_value.cluster_embeddings_with_radius.return_value = [
            {"group_id": "GroupA", "session_ids": ["0", "1"]},
            {"group_id": "GroupB", "session_ids": ["2"]},
        ]

        result = textual_consistency_instance.calculate_consistency(data)

        mock_calculate_consistency_with_confidence.assert_called_once()
        _args, kwargs = mock_calculate_consistency_with_confidence.call_args
        assert np.array_equal(kwargs["sample"], np.asarray(data))

        mock_format_consistency_result.assert_called_once()
        args, kwargs = mock_format_consistency_result.call_args
        assert args[0] == {"mean": 0.5, "confidence_interval": (0.4, 0.6)}
        assert np.isclose(
            args[1], np.log(textual_consistency_instance.sample_size)
        )  # max_score for entropy is log(sample_size)
        assert args[2] == "entropy"

        assert isinstance(result, ConsistencyResult)
        assert result.mean == 0.7

    def test_calculate_consistency_empty_data(self, textual_consistency_instance):
        data = []
        result = textual_consistency_instance.calculate_consistency(data)
        assert isinstance(result, ConsistencyResult)
        assert np.isnan(result.mean)
        assert np.isnan(result.confidence_interval[0])
