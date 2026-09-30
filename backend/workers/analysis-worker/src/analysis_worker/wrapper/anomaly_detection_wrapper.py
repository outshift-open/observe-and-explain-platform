#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import logging
from typing import Any, Dict, List

from dem.anomaly import AnomalyDetectionSessions
from dem.anomaly.graph_detector import GraphAnomalyDetector
from dem.anomaly.metric_detector import MetricAnomalyDetector
from dem.anomaly.textual_detector import TextualAnomalyDetector
from dem.utils.graph_utils import execution_graph_to_nx_graph
from oxp_ontology.models.nodes.anomaly_report import AnomalyReport
from worker_base.queue_message import SessionDetail

logger = logging.getLogger(__name__)

DEFAULT_LAYERS: Dict[str, Dict[str, Any]] = {
    "text": {"model_name": "isolation_forest"},
    "graph": {"model_name": "isolation_forest"},
    "metric": {"model_name": "elliptic_envelop"},
}


class AnomalyDetectionWrapper:
    def __init__(self, debug: bool = False, layers: Dict[str, Any] = None):
        self.debug = debug
        self.layers = layers if layers is not None else DEFAULT_LAYERS

    def process_group(self, analysis_data: List[SessionDetail]) -> List[AnomalyDetectionSessions]:
        anomalies = []
        for layer_name, settings in self.layers.items():
            model = (settings or {}).get("model_name", DEFAULT_LAYERS.get(layer_name, {}).get("model_name"))
            if layer_name == "text":
                res = self._detect_text_anomalies(analysis_data, model)
            elif layer_name == "graph":
                res = self._detect_graph_anomalies(analysis_data, model)
            elif layer_name == "metric":
                res = self._detect_metric_anomalies(analysis_data, model)
            else:
                res = None
            if res:
                anomalies.extend(res)
        return anomalies

    def _detect_text_anomalies(self, data: List[SessionDetail], model: str = None):
        logger.debug("Detect textual anomalies: %d sessions.", len(data))
        detector = TextualAnomalyDetector(model_name=model)
        texts, session_ids = [], []
        for s in data:
            if s.output_embedding:
                session_ids.append(s.session_id)
                texts.append(s.output_embedding)
        if not texts:
            return None
        result = detector.detect_outliers(texts)
        return [
            AnomalyDetectionSessions(
                inlier_sessions=[session_ids[i] for i in result.inliers_indices],
                outlier_sessions=[session_ids[i] for i in result.outliers_indices],
                reason="Anomalies detected in text embeddings",
                layer="text",
                scores=result.scores,
                threshold=result.threshold,
                metadata={"model_name": model},
            )
        ]

    def _detect_graph_anomalies(self, data: List[SessionDetail], model: str = None):
        logger.debug("Detect graph anomalies: %d sessions.", len(data))
        detector = GraphAnomalyDetector(model_name=model)
        graphs, session_ids = [], []
        for s in data:
            if s.execution_graph:
                graphs.append(execution_graph_to_nx_graph(s.execution_graph))
                session_ids.append(s.session_id)
        if not graphs:
            return None
        result = detector.detect_outliers(graphs)
        return [
            AnomalyDetectionSessions(
                inlier_sessions=[session_ids[i] for i in result.inliers_indices],
                outlier_sessions=[session_ids[i] for i in result.outliers_indices],
                reason="Anomalies detected in graph structure",
                layer="graph",
                scores=result.scores,
                threshold=result.threshold,
                metadata={"model_name": model},
            )
        ]

    def _detect_metric_anomalies(self, data: List[SessionDetail], model: str = None):
        logger.debug("Detect metric anomalies: %d sessions.", len(data))
        detector = MetricAnomalyDetector(model_name=model)
        metrics: Dict[str, Any] = {}
        for s in data:
            if s.metrics:
                for m, val in s.metrics.items():
                    if m not in metrics:
                        metrics[m] = {"session_ids": [], "values": []}
                    metrics[m]["session_ids"].append(s.session_id)
                    metrics[m]["values"].append(val)
        if not metrics:
            return None
        msgs = []
        for m, m_data in metrics.items():
            result = detector.detect_outliers(m_data["values"])
            msgs.append(
                AnomalyDetectionSessions(
                    inlier_sessions=[m_data["session_ids"][i] for i in result.inliers_indices],
                    outlier_sessions=[m_data["session_ids"][i] for i in result.outliers_indices],
                    reason=f"Anomalies detected in metric {m}",
                    layer="metric",
                    scores=result.scores,
                    threshold=result.threshold,
                    metadata={"model_name": model, "metric": m},
                )
            )
        return msgs

    @staticmethod
    def _compute_node_hash(inliers_values: List[str], outliers_values: List[str]) -> str:
        all_session_ids = sorted(set((inliers_values or []) + (outliers_values or [])))
        return hashlib.sha256(",".join(all_session_ids).encode()).hexdigest()

    def ingest_anomaly_report(
        self,
        kg_dal,
        anomaly_report: List[AnomalyDetectionSessions],
        group_id: str,
        node_hash: str = "",
    ) -> bool:
        all_ok = True
        for report in anomaly_report:
            metadata = report.metadata or {}
            metric_name = metadata.get("metric", "")
            report_id = hashlib.sha256((str(group_id) + str(report.layer) + str(metric_name)).encode()).hexdigest()
            report_node_hash = node_hash or self._compute_node_hash(report.inlier_sessions, report.outlier_sessions)
            threshold = report.threshold if report.threshold is not None else 0.0
            node = AnomalyReport(
                id=report_id,
                dataType=report.layer,
                scores=json.dumps(report.scores),
                threshold=threshold,
                ofSemanticGroup=group_id,
                **({"aboutMetric": metric_name} if report.layer == "metric" else {}),
            )
            if not kg_dal.ingest_anomaly_report(
                group_id=group_id,
                group_hash=report_node_hash,
                anomaly_report=node,
                source=report,
            ):
                all_ok = False
        return all_ok
