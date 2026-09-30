#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import MagicMock

import numpy as np
import pytest

from dem.consistency import Consistency, ConsistencyResult


# Helper class to test abstract Consistency class
class ConcreteConsistency(Consistency):
    def calculate_consistency(self, data: any) -> ConsistencyResult:
        # Dummy implementation for testing purposes
        return ConsistencyResult(mean=0.5, confidence_interval=(0.4, 0.6))


# A specific concrete class for testing the Consistency's __init__ method
class _ConcreteConsistencyForInitTest(Consistency):
    def calculate_consistency(self, data: any) -> ConsistencyResult:
        raise NotImplementedError("This method should not be called in init tests.")


@pytest.fixture
def consistency_instance():
    return ConcreteConsistency()


@pytest.fixture
def consistency_base_instance_for_non_abstract_methods():
    # This fixture is for testing non-abstract methods that don't depend on calculate_consistency
    # being fully functional, but need an instantiated Consistency object.
    # We temporarily make it non-abstract to instantiate, then restore.
    original_abstract_methods = Consistency.__abstractmethods__
    Consistency.__abstractmethods__ = set()
    # Provide default valid parameters for instantiation
    instance = Consistency(
        statistic="std",
        confidence_level=95,
        sample_size=1,
        N_nearest_neighbors=1,
        N_bootstrap_samples=1,
    )
    Consistency.__abstractmethods__ = (
        original_abstract_methods  # Reset after instantiation
    )
    return instance


class TestConsistencyInit:
    def test_valid_initialization(self):
        # Directly instantiate the concrete test class
        consistency = _ConcreteConsistencyForInitTest(
            statistic="std",
            confidence_level=95,
            sample_size=10,
            N_nearest_neighbors=100,
            N_bootstrap_samples=2000,
        )
        assert consistency.statistic == "std"
        assert consistency.confidence_level == 95
        assert consistency.sample_size == 10
        assert consistency.N_nearest_neighbors == 100
        assert consistency.N_bootstrap_samples == 2000

    @pytest.mark.parametrize(
        "statistic, confidence_level, sample_size, N_nearest_neighbors, N_bootstrap_samples, expected_error",
        [
            ("", -1, 10, 100, 2000, "statitic function name is required"),
            ("std", -1, 10, 100, 2000, "confidence_level should be in [0,100]"),
            ("std", 101, 10, 100, 2000, "confidence_level should be in [0,100]"),
            ("std", 95, 0, 100, 2000, "sample_size should be at least 1."),
            ("std", 95, 10, 5, 2000, "sample_size cannot exceed N_nearest_neighbors"),
            ("std", 95, 10, 100, 0, "N_bootstrap_samples should be at least 1."),
        ],
    )
    def test_invalid_initialization(
        self,
        statistic,
        confidence_level,
        sample_size,
        N_nearest_neighbors,
        N_bootstrap_samples,
        expected_error,
    ):
        with pytest.raises(ValueError) as excinfo:
            # Directly instantiate the concrete test class
            _ConcreteConsistencyForInitTest(
                statistic=statistic,
                confidence_level=confidence_level,
                sample_size=sample_size,
                N_nearest_neighbors=N_nearest_neighbors,
                N_bootstrap_samples=N_bootstrap_samples,
            )
        assert expected_error in str(excinfo.value)


class TestConsistencyBootstrapSamples:
    @pytest.mark.parametrize(
        "sample_data, N_original_sample_elements, sample_size, N_bootstrap_samples, expected_shape",
        [
            (np.array([1, 2, 3, 4, 5]), 5, 3, 2, (2, 3)),
            (np.array([[1, 1], [2, 2], [3, 3]]), 3, 2, 3, (3, 2, 2)),
            (np.array([10]), 1, 1, 1, (1, 1)),
            (np.array([]), 0, 5, 10, (10, 5)),  # Empty sample
            (np.array([1, 2, 3]), 3, 1, 1, (1, 1)),
            (np.array([1, 2, 3]), 3, 3, 1, (1, 3)),
            (
                np.array([1, 2, 3]),
                3,
                5,
                10,
                (10, 5),
            ),  # sample_size > N_original_sample_elements
        ],
    )
    def test_generate_bootstrap_samples(
        self,
        consistency_base_instance_for_non_abstract_methods,  # Use fixture
        monkeypatch,
        sample_data,
        N_original_sample_elements,
        sample_size,
        N_bootstrap_samples,
        expected_shape,
    ):
        consistency_base_instance_for_non_abstract_methods.sample_size = sample_size
        consistency_base_instance_for_non_abstract_methods.N_bootstrap_samples = (
            N_bootstrap_samples
        )
        consistency_base_instance_for_non_abstract_methods.N_nearest_neighbors = max(
            N_original_sample_elements, sample_size, 1
        )  # Ensure valid init, min 1

        # Mock np.random.multinomial for deterministic testing
        if N_original_sample_elements > 0:

            def mock_multinomial_side_effect(n, pvals, size):
                num_elements = len(pvals)
                result = np.zeros((size, num_elements), dtype=int)
                for i in range(size):
                    # Simulate sampling with replacement
                    chosen_indices = np.random.choice(
                        num_elements, size=n, replace=True
                    )
                    for idx in chosen_indices:
                        result[i, idx] += 1
                return result

            monkeypatch.setattr(
                "numpy.random.multinomial", mock_multinomial_side_effect, raising=True
            )

        # _generate_bootstrap_samples now returns a generator, so we need to consume it
        bootstrap_samples_gen = consistency_base_instance_for_non_abstract_methods._generate_bootstrap_samples(
            sample=sample_data
        )
        bootstrap_samples = list(bootstrap_samples_gen)  # Consume the generator

        # Check that we have the correct number of samples
        assert len(bootstrap_samples) == expected_shape[0]

        if bootstrap_samples:  # If we have samples
            # Check the shape of each individual sample
            first_sample = np.asarray(bootstrap_samples[0])
            assert first_sample.shape == expected_shape[1:]

        if sample_data.size > 0 and N_original_sample_elements > 0 and sample_size > 0:
            original_elements = (
                [tuple(x) for x in sample_data.reshape(-1, sample_data.shape[-1])]
                if sample_data.ndim > 1
                else list(sample_data)
            )

            for bs_sample_row in bootstrap_samples:
                bs_array = np.asarray(bs_sample_row)
                for element in bs_array:
                    if sample_data.ndim > 1:
                        assert tuple(element) in original_elements
                    else:
                        assert element in original_elements
        elif sample_data.size == 0 and expected_shape[1] > 0:
            for bs_sample in bootstrap_samples:
                bs_array = np.asarray(bs_sample)
                assert np.all(
                    bs_array
                    == np.zeros(
                        expected_shape[1:],
                        dtype=sample_data.dtype if sample_data.dtype else float,
                    )
                )


class TestConsistencyConfidenceInterval:
    @pytest.mark.parametrize(
        "results, confidence_level, expected_interval",
        [
            (
                np.array([10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
                90,
                [14.5, 95.5],
            ),
            (
                np.array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]),
                95,
                [1.225, 9.775],
            ),
            (np.array([50, 50, 50, 50, 50]), 95, [50.0, 50.0]),
            (np.array([0, 100]), 50, [25.0, 75.0]),
            (np.array([10]), 95, [10.0, 10.0]),
        ],
    )
    def test_calculate_confidence_interval(
        self,
        consistency_base_instance_for_non_abstract_methods,
        results,
        confidence_level,
        expected_interval,
    ):
        consistency_base_instance_for_non_abstract_methods.confidence_level = (
            confidence_level
        )
        lower, upper = (
            consistency_base_instance_for_non_abstract_methods._calculate_confidence_interval(
                results
            )
        )
        assert np.isclose(lower, expected_interval[0])
        assert np.isclose(upper, expected_interval[1])


class TestConsistencyWithConfidence:
    def test_calculate_consistency_with_confidence_basic(
        self, consistency_base_instance_for_non_abstract_methods, monkeypatch
    ):
        sample = np.array([1, 2, 3, 4, 5])
        consistency_base_instance_for_non_abstract_methods.sample_size = 3
        consistency_base_instance_for_non_abstract_methods.N_bootstrap_samples = 10
        consistency_base_instance_for_non_abstract_methods.confidence_level = 90
        consistency_base_instance_for_non_abstract_methods.N_nearest_neighbors = 5

        # Mock internal methods
        mock_bootstrap_samples = np.array([[1, 2, 3], [2, 3, 4], [3, 4, 5]])
        mock_gen = MagicMock(return_value=mock_bootstrap_samples)
        monkeypatch.setattr(
            consistency_base_instance_for_non_abstract_methods,
            "_generate_bootstrap_samples",
            mock_gen,
        )

        mock_statistic_results = np.array([1.0, 2.0, 3.0])

        def mock_statistic_function(original_sample, bootstraps):
            return mock_statistic_results

        consistency_base_instance_for_non_abstract_methods.statistic_function = (
            mock_statistic_function
        )
        mock_confidence_interval = (1.1, 2.9)
        mock_ci = MagicMock(return_value=mock_confidence_interval)
        monkeypatch.setattr(
            consistency_base_instance_for_non_abstract_methods,
            "_calculate_confidence_interval",
            mock_ci,
        )

        result = consistency_base_instance_for_non_abstract_methods._calculate_consistency_with_confidence(
            sample=sample
        )

        assert result["mean"] == np.mean(mock_statistic_results).item()
        assert result["confidence_interval"] == mock_confidence_interval
        consistency_base_instance_for_non_abstract_methods._generate_bootstrap_samples.assert_called_once_with(
            sample=sample
        )
        consistency_base_instance_for_non_abstract_methods._calculate_confidence_interval.assert_called_once_with(
            mock_statistic_results
        )

    def test_calculate_consistency_with_confidence_empty_sample(
        self, consistency_base_instance_for_non_abstract_methods
    ):
        sample = np.array([])
        consistency_base_instance_for_non_abstract_methods.sample_size = 1
        consistency_base_instance_for_non_abstract_methods.N_bootstrap_samples = 1
        consistency_base_instance_for_non_abstract_methods.N_nearest_neighbors = 1

        def dummy_statistic_function(original_sample, bootstraps):
            return np.array([])

        consistency_base_instance_for_non_abstract_methods.statistic_function = (
            dummy_statistic_function
        )

        result = consistency_base_instance_for_non_abstract_methods._calculate_consistency_with_confidence(
            sample=sample
        )

        assert np.isnan(result["mean"])
        assert np.isnan(result["confidence_interval"][0])
        assert np.isnan(result["confidence_interval"][1])


class TestConsistencyFormatResult:
    @pytest.mark.parametrize(
        "consistency_with_conf, max_score, statistic, normalize, expected_res_mean, expected_res_ci, expected_indicator",
        [
            # Test case 1: ci_width = 0.2, max_score = 1.0 -> relative_width = 0.2 -> "Low"
            (
                {"mean": 0.2, "confidence_interval": (0.1, 0.3)},
                1.0,
                "std",
                True,
                0.8,
                (0.7, 0.9),
                "Low",
            ),
            # Test case 2: ci_width = 20.0, max_score = 100.0 -> relative_width = 0.2 -> "Low"
            (
                {"mean": 20.0, "confidence_interval": (10.0, 30.0)},
                100.0,
                "std",
                False,
                80.0,
                (70.0, 90.0),
                "Low",
            ),
            # Test case 3: ci_width = 0.3, max_score = 1.0 -> relative_width = 0.3 -> "Low"
            (
                {"mean": 0.2, "confidence_interval": (0.05, 0.35)},
                1.0,
                "std",
                True,
                0.8,
                (0.65, 0.95),
                "Low",
            ),
            # Test case for "High" confidence: relative_width < 0.05
            (
                {"mean": 0.1, "confidence_interval": (0.09, 0.11)},
                1.0,
                "std",
                True,
                0.9,
                (0.89, 0.91),
                "High",
            ),
            # Test case for "Medium" confidence: 0.05 <= relative_width < 0.15
            (
                {"mean": 0.1, "confidence_interval": (0.05, 0.15)},
                1.0,
                "std",
                True,
                0.9,
                (0.85, 0.95),
                "Medium",
            ),
            # Low confidence (boundary check)
            (
                {"mean": 0.2, "confidence_interval": (0.0, 0.4)},
                1.0,
                "std",
                True,
                0.8,
                (0.6, 1.0),
                "Low",
            ),
            # max_score = 0, normalize=True (special handling)
            (
                {"mean": 0.0, "confidence_interval": (0.0, 0.0)},
                0.0,
                "std",
                True,
                0.0,
                (0.0, 0.0),
                "High",
            ),
            # max_score = 0, normalize=False (should only happen if metric legitimately has max 0)
            (
                {"mean": 0.0, "confidence_interval": (0.0, 0.0)},
                0.0,
                "std",
                False,
                0.0,
                (0.0, 0.0),
                "High",
            ),
            # max_score > 0 but ci_width is 0
            (
                {"mean": 0.1, "confidence_interval": (0.1, 0.1)},
                1.0,
                "std",
                True,
                0.9,
                (0.9, 0.9),
                "High",
            ),
        ],
    )
    def test_format_consistency_result(
        self,
        consistency_base_instance_for_non_abstract_methods,
        consistency_with_conf,
        max_score,
        statistic,
        normalize,
        expected_res_mean,
        expected_res_ci,
        expected_indicator,
    ):
        result = consistency_base_instance_for_non_abstract_methods._format_consistency_result(
            consistency_with_conf, max_score, normalize
        )

        assert isinstance(result, ConsistencyResult)
        assert np.isclose(result.mean, expected_res_mean)
        assert np.isclose(result.confidence_interval[0], expected_res_ci[0])
        assert np.isclose(result.confidence_interval[1], expected_res_ci[1])
        assert result.confidence_indicator == expected_indicator
        assert result.statistic == statistic
        if normalize and max_score > 0:
            assert result.max == 1.0
        elif not normalize and max_score > 0:
            assert result.max == max_score
        elif max_score == 0:
            assert result.max == 0.0

    def test_format_consistency_result_max_score_zero_non_normalized(
        self, consistency_base_instance_for_non_abstract_methods
    ):
        # Specific test for max_score=0 and normalize=False, where ci_width could be > 0 (problematic)
        # In this case, relative_width should be 0, and indicator High.
        consistency_with_conf = {"mean": 0.0, "confidence_interval": (0.0, 0.0)}
        max_score = 0.0
        normalize = False
        result = consistency_base_instance_for_non_abstract_methods._format_consistency_result(
            consistency_with_conf, max_score, normalize
        )
        assert result.confidence_indicator == "High"
        assert result.mean == 0.0
        assert result.confidence_interval == (0.0, 0.0)


class TestConsistencyAbstractMethod:
    def test_calculate_consistency_is_abstract(self):
        # Cannot instantiate Consistency directly because it has abstract methods
        with pytest.raises(
            TypeError,
            match="Can't instantiate abstract class Consistency without an implementation for abstract method 'calculate_consistency'",
        ):
            Consistency(statistic="std")

        # Test that calling the abstract method on a concrete class works
        instance = ConcreteConsistency(statistic="std")
        result = instance.calculate_consistency(data=[1, 2, 3])
        assert isinstance(result, ConsistencyResult)
        assert result.mean == 0.5
