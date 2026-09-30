#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from typing import Any, List, Optional

from pydantic import BaseModel, Field


class AnomalyDetectionResult(BaseModel):
    """
    A class to encapsulate the results of an anomaly detection process,
    including indices and values of inliers and outliers.
    """

    inliers_indices: List[int] = Field(default=[])
    inliers_values: List[Any] = Field(default=[])
    outliers_indices: List[int] = Field(default=[])
    outliers_values: List[Any] = Field(default=[])
    scores: List[float] = Field(default=[])
    threshold: Optional[float] = Field(default=None)
    model_name: Optional[str] = None


class AnomalyDetectionSessions(BaseModel):
    """
    A class to represent a session with its associated data for anomaly detection.
    """

    inlier_sessions: Optional[List[str]] = None
    outlier_sessions: Optional[List[str]] = None
    reason: Optional[str] = None
    layer: Optional[str] = None

    scores: List[float] = Field(default=[])
    threshold: Optional[float] = Field(default=None)
    metadata: Optional[dict] = None
