#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional, Union

from dem.consistency import ConsistencySessions
from dem.consistency.graph_consistency import GraphConsistency
from dem.consistency.metric_consistency import MetricConsistency
from dem.consistency.textual_consistency import TextualConsistency
from dem.utils.graph_utils import execution_graph_to_nx_graph
from oxp_ontology.models.nodes.consistency_report import ConsistencyReport
from worker_base.queue_message import SessionDetail

logger = logging.getLogger(__name__)

DEFAULT_LAYERS: Dict[str, Dict[str, Any]] = {
    "text": {"statistic": "dispersion"},
    "graph": {"statistic": "average_pairwise_wl_distance"},
    "metric": {"statistic": "std"},
}


class ConsistencyWrapper:
    def __init__(self, debug: bool = False, layers: Dict[str, Any] = None):
        self.debug = debug
        self.layers = layers if layers is not None else DEFAULT_LAYERS
        # Apply defaults for any layer that has an empty config
        for layer in self.layers:
            if layer in DEFAULT_LAYERS and not self.layers[layer]:
                self.layers[layer] = DEFAULT_LAYERS[layer]

    def process_group(self, analysis_data: List[SessionDetail]) -> List[ConsistencySessions]:
        if not analysis_data or len(analysis_data) <= 1:
            logger.warning("Not enough sessions in the group to compute consistency.")
            return []

        reports = []
        for layer_name, settings in self.layers.items():
            logger.debug("Processing consistency layer: %s %s", layer_name, settings)
            if layer_name == "text":
                res = self._compute_text(analysis_data, settings)
            elif layer_name == "graph":
                res = self._compute_graph(analysis_data, settings)
            elif layer_name == "metric":
                res = self._compute_metric(analysis_data, settings)
            else:
                res = None
            if res:
                reports.extend(res)
        return reports

    def _detector_kwargs(self, settings: dict) -> dict:
        keys = ["statistic", "confidence_level", "sample_size", "N_nearest_neighbors", "N_bootstrap_samples"]
        return {k: settings[k] for k in keys if k in settings and settings[k] is not None}

    def _compute_text(self, data: List[SessionDetail], settings: dict):
        kwargs = self._detector_kwargs(settings)
        detector = TextualConsistency(**kwargs)
        texts, session_ids = [], []
        for s in data:
            if s.output_embedding:
                session_ids.append(s.session_id)
                texts.append(s.output_embedding)
        if not texts:
            return None
        result = detector.calculate_consistency(texts)
        return [ConsistencySessions(consistency_result=result, session_ids=session_ids, layer="text", metadata=kwargs)]

    def _compute_graph(self, data: List[SessionDetail], settings: dict):
        kwargs = self._detector_kwargs(settings)
        detector = GraphConsistency(**kwargs)
        graphs, session_ids = [], []
        for s in data:
            if s.execution_graph:
                graphs.append(execution_graph_to_nx_graph(s.execution_graph))
                session_ids.append(s.session_id)
        if not graphs:
            return None
        result = detector.calculate_consistency(graphs)
        return [ConsistencySessions(consistency_result=result, session_ids=session_ids, layer="graph", metadata=kwargs)]

    def _compute_metric(self, data: List[SessionDetail], settings: dict):
        kwargs = self._detector_kwargs(settings)
        detector = MetricConsistency(**kwargs)
        metrics: Dict[str, Any] = {}
        for s in data:
            if s.metrics:
                for m, val in s.metrics.items():
                    if m not in metrics:
                        metrics[m] = {"session_ids": [], "values": []}
                    metrics[m]["session_ids"].append(s.session_id)
                    # Extract numeric value from potentially stringified JSON metric object
                    numeric_value = self._extract_metric_value(val)
                    if numeric_value is not None:
                        metrics[m]["values"].append(numeric_value)
        if not metrics:
            return None
        msgs = []
        for m, m_data in metrics.items():
            # Only process if we have values
            if m_data["values"]:
                result = detector.calculate_consistency(m_data["values"])
                msgs.append(
                    ConsistencySessions(
                        consistency_result=result,
                        session_ids=m_data["session_ids"],
                        layer="metric",
                        metadata={**kwargs, "metric": m},
                    )
                )
        return msgs

    @staticmethod
    def _extract_metric_value(metric: Union[str, dict, float, int]) -> Optional[float]:
        """
        Extract numeric value from a metric that may be:
        - A plain number (float/int)
        - A dict with a 'value' field
        - A stringified JSON object with a 'value' field

        Returns:
            The numeric value if extractable, None otherwise.
        """
        # If already a number, return it
        if isinstance(metric, (int, float)):
            return float(metric)

        # If it's a string, try to parse as JSON
        if isinstance(metric, str):
            try:
                parsed = json.loads(metric)
                if isinstance(parsed, dict) and "value" in parsed:
                    val = parsed["value"]
                    return float(val) if isinstance(val, (int, float)) else None
                elif isinstance(parsed, (int, float)):
                    return float(parsed)
            except (json.JSONDecodeError, ValueError, TypeError):
                # If parsing fails, try direct float conversion
                try:
                    return float(metric)
                except ValueError:
                    return None

        # If it's a dict, extract the 'value' field
        if isinstance(metric, dict):
            if "value" in metric:
                val = metric["value"]
                return float(val) if isinstance(val, (int, float)) else None

        return None

    def ingest_consistency(
        self, kg_dal, reports: List[ConsistencySessions], group_id: str, node_hash: str = ""
    ) -> bool:
        all_ok = True
        for report in reports:
            metadata = report.metadata or {}
            report_id = hashlib.sha256(
                (str(group_id) + str(report.layer) + str(metadata.get("metric", ""))).encode()
            ).hexdigest()
            node = ConsistencyReport(
                id=report_id,
                dataType=report.layer,
                mean=report.consistency_result.mean,
                confidenceInterval=json.dumps(report.consistency_result.confidence_interval),
                confidenceIndicator=report.consistency_result.confidence_indicator,
                ofSemanticGroup=group_id,
                **({"aboutMetric": metadata.get("metric", "")} if report.layer == "metric" else {}),
            )
            if not kg_dal.ingest_consistency_report(
                group_id=group_id, group_hash=node_hash, consistency_report=node, source=report
            ):
                all_ok = False
        return all_ok
