#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Dict, List, Optional, Tuple

import numpy as np
from pydantic import BaseModel, Field


class ConsistencyResult(BaseModel):
    """
    A class to encapsulate the results of a consistency computation, with confidence
    interval and indicator.

    Attributes:
        min (float): The minimum possible value for the consistency metric.
        max (float): The maximum possible value for the consistency metric.
        mean (float): The calculated mean consistency score.
        confidence_interval (Tuple[float, float]): A tuple representing the lower and upper bounds
                                                   of the confidence interval for the consistency score.
        confidence_indicator (str): A qualitative indicator of the confidence interval width (e.g., "High", "Medium", "Low").
        statistic (str): The name of the statistic used for consistency calculation (e.g., "std", "dispersion").
    """

    min: float = Field(default=np.nan)
    max: float = Field(default=np.nan)
    mean: float = Field(default=np.nan)
    confidence_interval: Tuple[float, float] = Field(default=(np.nan, np.nan))
    confidence_indicator: str = Field(default="")
    statistic: str = Field(default="")


class ConsistencySessions(BaseModel):
    """
    A class to represent a session with its associated data for consistentcy computation.
    """

    consistency_result: ConsistencyResult
    session_ids: Optional[List[str]] = Field(default=None)
    metadata: Optional[Dict[str, str]] = Field(default=None)
    layer: Optional[str] = Field(default=None)
