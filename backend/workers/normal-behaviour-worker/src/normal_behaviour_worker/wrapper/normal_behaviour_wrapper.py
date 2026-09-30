#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from typing import Any, Dict, List, Optional

from dem.normal_behaviour.normal_graph import GraphNormalBehaviour
from dem.normal_behaviour.normal_metric import MetricNormalBehaviour
from dem.normal_behaviour.normal_textual import TextNormalBehaviour
from dem.normal_behaviour.utils import NormalBehaviourSessions
from dem.utils.graph_utils import execution_graph_to_nx_graph
from worker_base.queue_message import SessionDetail

DEFAULT_LAYER: Dict[str, Any] = {
    "text": {"statistic": "gaussian"},
    "graph": {"statistic": "consensus"},
    "metric": {"statistic": "gaussian"},
}


class NormalBehaviourWrapper:
    def __init__(self, debug: bool = False, layers: Optional[Dict[str, Any]] = None):
        self.debug = debug
        self.layers = layers if layers is not None else DEFAULT_LAYER
        for layer in self.layers:
            if layer in DEFAULT_LAYER:
                if self.layers[layer] is None or len(self.layers[layer]) == 0:
                    self.layers[layer] = DEFAULT_LAYER[layer]

    def process_group(self, analysis_data: List[SessionDetail]) -> List[NormalBehaviourSessions]:
        if analysis_data is None or len(analysis_data) <= 1:
            return []

        results = []
        for layer_name, setting in self.layers.items():
            if layer_name == "text":
                res = self._compute_text_normal(analysis_data, setting)
            elif layer_name == "graph":
                res = self._compute_graph_normal(analysis_data, setting)
            elif layer_name == "metric":
                res = self._compute_metric_normal(analysis_data, setting)
            else:
                res = None
            if res:
                results.extend(res)
        return results

    def _compute_text_normal(
        self, data: List[SessionDetail], setting: dict = {}
    ) -> Optional[List[NormalBehaviourSessions]]:
        kwargs = {k: setting[k] for k in ["statistic"] if k in setting and setting[k] is not None}
        detector = TextNormalBehaviour(**kwargs)
        session_ids, embedding_data, text_data = [], [], []
        for s in data:
            if s.output_embedding and len(s.output_embedding) > 0:
                session_ids.append(s.session_id)
                embedding_data.append(s.output_embedding)
                text_data.append(s.output_content)
        if not embedding_data:
            return None
        report = detector.calculate_normal_behaviour(embedding_data, text_data)
        return [
            NormalBehaviourSessions(normal_behaviour=report, session_ids=session_ids, layer="text", metadata=kwargs)
        ]

    def _compute_graph_normal(
        self, data: List[SessionDetail], setting: dict = {}
    ) -> Optional[List[NormalBehaviourSessions]]:
        kwargs = {
            k: setting[k]
            for k in ["statistic", "majority_threshold", "get_closest_sample"]
            if k in setting and setting[k] is not None
        }
        detector = GraphNormalBehaviour(**kwargs)
        session_ids, graph_data = [], []
        for s in data:
            if s.execution_graph and len(s.execution_graph) > 0:
                session_ids.append(s.session_id)
                graph_data.append(execution_graph_to_nx_graph(s.execution_graph))
        if not graph_data:
            return None
        report = detector.calculate_normal_behaviour(graph_data)
        return [
            NormalBehaviourSessions(normal_behaviour=report, session_ids=session_ids, layer="graph", metadata=kwargs)
        ]

    def _compute_metric_normal(
        self, data: List[SessionDetail], setting: dict = {}
    ) -> Optional[List[NormalBehaviourSessions]]:
        kwargs = {k: setting[k] for k in ["statistic"] if k in setting and setting[k] is not None}
        detector = MetricNormalBehaviour(**kwargs)
        metrics: Dict[str, Any] = {}
        for s in data:
            if s.metrics:
                for m, v in s.metrics.items():
                    if m not in metrics:
                        metrics[m] = {"session_ids": [], "metrics_data": []}
                    metrics[m]["session_ids"].append(s.session_id)
                    metrics[m]["metrics_data"].append(v)
        if not metrics:
            return None
        results = []
        for m, mdata in metrics.items():
            report = detector.calculate_normal_behaviour(mdata["metrics_data"])
            results.append(
                NormalBehaviourSessions(
                    normal_behaviour=report,
                    session_ids=mdata["session_ids"],
                    layer="metric",
                    metadata={**kwargs, "metric": m},
                )
            )
        return results
