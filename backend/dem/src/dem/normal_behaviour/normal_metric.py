#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Sequence
import numpy as np

from dem.normal_behaviour.base import NormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourResultMetric


class MetricNormalBehaviour(NormalBehaviour):
    def __init__(
        self,
        statistic: str,
    ):
        super().__init__(statistic)

    def calculate_normal_behaviour(
        self, data: Sequence[float]
    ) -> NormalBehaviourResultMetric:
        if not data:
            # Return an empty/default result if no data is provided
            return NormalBehaviourResultMetric()

        sample = np.asarray(data)

        if self.statistic == "gaussian":
            result_data = self._calculate_normal_behaviour_gaussian(sample)
        elif self.statistic == "quantiles":
            result_data = self._calculate_normal_behaviour_quantiles(sample)
        elif self.statistic == "var_based":
            result_data = self._calculate_normal_behaviour_by_var(sample)
        else:
            raise ValueError(f"Unknown statistic: {self.statistic}")

        result_data.statistic = self.statistic
        result_data.representative_sample = result_data.centroid
        return result_data
