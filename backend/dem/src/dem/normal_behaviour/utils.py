#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union


# Generic class for defining normal behaviour results
# Can be extended for specific types of data (e.g., text, metrics, etc.)
class NormalBehaviourResult(BaseModel):
    centroid: Optional[object] = Field(
        default=None
    )  # matematically central point of the distribution, can be a vector for multidimensional data
    representative_sample: Optional[object] = Field(
        default=None
    )  # can be used to define the closes element in the distribution to the centroid, or the medoid, etc. depending on the statistic used
    statistic: Optional[str] = Field(default="")
    other_info: Optional[Dict[str, object]] = Field(default=None)


class NormalBehaviourResultText(NormalBehaviourResult):
    centroid: Optional[List[float]] = Field(default=None)  # embeddings
    representative_sample: Optional[List[float]] = Field(default=None)  # text

    representative_processed_sample: Optional[str] = Field(default=None)  # text
    upper: Optional[List[float]] = Field(default=None)
    lower: Optional[List[float]] = Field(default=None)
    std: Optional[List[float]] = Field(default=None)
    variance: Optional[List[float]] = Field(default=None)
    mean: Optional[List[float]] = Field(default=None)
    median: Optional[List[float]] = Field(default=None)


class NormalBehaviourResultMetric(NormalBehaviourResult):
    centroid: Optional[float] = Field(default=None)
    representative_sample: Optional[float] = Field(default=None)

    upper: Optional[float] = Field(default=None)
    lower: Optional[float] = Field(default=None)
    std: Optional[float] = Field(default=None)
    variance: Optional[float] = Field(default=None)
    mean: Optional[float] = Field(default=None)
    median: Optional[float] = Field(default=None)


class NormalBehaviourResultGraph(NormalBehaviourResult):
    centroid: Optional[Dict[str, object]] = Field(
        default=None
    )  # form {nodes: [...], edges: [...]} see nx_graph_to_dict
    representative_sample: Optional[Dict[str, object]] = Field(
        default=None
    )  # form {nodes: [...], edges: [...]} see nx_graph_to_dict


class NormalBehaviourSessions(BaseModel):
    normal_behaviour: Union[
        NormalBehaviourResult,
        NormalBehaviourResultText,
        NormalBehaviourResultGraph,
        NormalBehaviourResultMetric,
    ]
    session_ids: Optional[List[str]] = Field(default=None)
    metadata: Optional[Dict[str, object]] = Field(default=None)
    layer: Optional[str] = Field(default=None)
