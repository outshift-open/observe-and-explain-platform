#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import multiprocessing
import os
import tempfile
from typing import Any, Dict, List, Optional

from oxp_ontology.models.nodes.anomaly_report import AnomalyReport
from oxp_ontology.models.nodes.consistency_report import ConsistencyReport
from oxp_ontology.models.nodes.normal_behaviour_report import NormalBehaviourReport
from worker_base.base_worker import BaseWorker
from worker_base.queue_message import (
    BaseQueueMessage,
    SessionDetail,
    SessionGroupMessage,
)

from analysis_worker.wrapper.anomaly_detection_wrapper import AnomalyDetectionWrapper
from analysis_worker.wrapper.consistency_wrapper import ConsistencyWrapper
from analysis_worker.wrapper.normal_behaviour_wrapper import NormalBehaviourWrapper

logger = logging.getLogger(__name__)


def _run_batch_analysis_process(
    worker_kwargs: Dict[str, Any],
    analysis_payload: List[Dict[str, Any]],
    msg_payload: Dict[str, Any],
    result_path: str,
):
    worker = None
    try:
        worker = AnalysisWorker(**worker_kwargs)
        analysis_data = [SessionDetail.model_validate(item) for item in analysis_payload]
        msg = SessionGroupMessage.model_validate(msg_payload)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            anomaly_future = executor.submit(worker._run_anomaly_sync, analysis_data, msg)
            consistency_future = executor.submit(worker._run_consistency_sync, analysis_data, msg)
            normal_behaviour_future = executor.submit(worker._run_normal_behaviour_sync, analysis_data, msg)

            anomalies = anomaly_future.result()
            consistency = consistency_future.result()
            normal_behaviour = normal_behaviour_future.result()

        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "ok": True,
                    "anomalies": anomalies,
                    "consistency": consistency,
                    "normal_behaviour": normal_behaviour,
                },
                handle,
            )
    except Exception as exc:
        logger.exception("Batch analysis subprocess failed: %s", exc)
        with open(result_path, "w", encoding="utf-8") as handle:
            json.dump({"ok": False, "error": str(exc)}, handle)
    finally:
        if worker is not None and worker.db_handler is not None:
            try:
                worker.db_handler.close()
            except Exception:
                logger.debug("Failed to close batch subprocess db handler", exc_info=True)


class AnalysisOutputMessage(BaseQueueMessage):
    group_id: str
    batch_index: int | None = None
    batch_session_count: int | None = None
    sessions: List[Dict[str, Any]] = []
    anomalies: List[Dict[str, Any]] = []
    consistency: List[Dict[str, Any]] = []
    normal_behaviour: List[Dict[str, Any]] = []


class AnalysisWorker(BaseWorker):
    """Combined worker that runs anomaly detection, consistency, and normal behaviour
    analyses concurrently for each message consumed from the queue.

    Args:
        n_workers: Maximum number of analysis sub-tasks that may run concurrently
            within a single message. Defaults to 3 (all analyses run at once).
        max_inflight_messages: Maximum number of queue messages processed in parallel.
        anomaly_layers: Layer configuration forwarded to AnomalyDetectionWrapper.
        consistency_layers: Layer configuration forwarded to ConsistencyWrapper.
        normal_behaviour_layers: Layer configuration forwarded to NormalBehaviourWrapper.
    """

    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        embedding_model: str,
        n_workers: int = 3,
        layers: Optional[Dict[str, Any]] = None,
        anomaly_layers: Optional[Dict[str, Any]] = None,
        consistency_layers: Optional[Dict[str, Any]] = None,
        normal_behaviour_layers: Optional[Dict[str, Any]] = None,
        output_queue: Optional[List[str]] = None,
        feedback_queue: Optional[str] = None,
        message_limit: int = -1,
        max_inflight_messages: int = 1,
        debug: bool = False,
        batch_size: int = 10,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )

        self.name = "AnalysisWorker"
        self.input_message_class = SessionGroupMessage
        self.embedding_model = embedding_model
        self.batch_size = batch_size
        self._skip_db_io = False
        self._semaphore = asyncio.Semaphore(max(1, n_workers))
        self._batch_subprocess_worker_kwargs = dict(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            embedding_model=embedding_model,
            n_workers=1,
            layers=layers,
            anomaly_layers=anomaly_layers,
            consistency_layers=consistency_layers,
            normal_behaviour_layers=normal_behaviour_layers,
            output_queue=[],
            feedback_queue=None,
            message_limit=-1,
            max_inflight_messages=1,
            debug=debug,
            batch_size=batch_size,
        )

        self.anomaly_wrapper = AnomalyDetectionWrapper(debug=debug, layers=anomaly_layers or layers)
        self.consistency_wrapper = ConsistencyWrapper(debug=debug, layers=consistency_layers or layers)
        self.normal_behaviour_wrapper = NormalBehaviourWrapper(debug=debug, layers=normal_behaviour_layers or layers)

    async def _run_batch_analysis_subprocess(
        self,
        analysis_data: List[SessionDetail],
        msg: SessionGroupMessage,
        batch_size: Optional[int] = None,
    ):
        if batch_size is None:
            batch_size = self.batch_size
        return await asyncio.to_thread(self._run_batch_analysis_subprocess_sync, analysis_data, msg, batch_size)

    def _run_batch_analysis_subprocess_sync(
        self,
        analysis_data: List[SessionDetail],
        msg: SessionGroupMessage,
        batch_size: int,
    ):
        ctx = multiprocessing.get_context("spawn")
        result_fd, result_path = tempfile.mkstemp(prefix="analysis-batch-", suffix=".json")
        os.close(result_fd)
        process = ctx.Process(
            target=_run_batch_analysis_process,
            args=(
                self._batch_subprocess_worker_kwargs,
                [item.model_dump() for item in analysis_data],
                msg.model_dump(by_alias=True),
                result_path,
            ),
        )
        process.start()
        process.join()

        if process.exitcode != 0:
            try:
                os.unlink(result_path)
            except FileNotFoundError:
                pass
            logger.warning(
                "Batch analysis subprocess failed with code %d, batch_size=%d, sessions=%d, retrying with smaller batch",
                process.exitcode,
                batch_size,
                len(analysis_data),
            )
            if batch_size <= 1:
                raise RuntimeError(
                    f"Batch analysis subprocess exited with code {process.exitcode} (batch_size already at minimum)"
                )
            smaller_batch_size = max(1, batch_size // 2)
            logger.info(
                "Retrying analysis with reduced batch_size: %d → %d",
                batch_size,
                smaller_batch_size,
            )
            return self._run_batch_analysis_with_retry_sync(
                analysis_data,
                msg,
                smaller_batch_size,
            )

        with open(result_path, "r", encoding="utf-8") as handle:
            result = json.load(handle)
        os.unlink(result_path)

        if not result.get("ok"):
            raise RuntimeError(result.get("error", "Unknown batch subprocess error"))

        return (
            result.get("anomalies") or [],
            result.get("consistency") or [],
            result.get("normal_behaviour") or [],
        )

    def _run_batch_analysis_with_retry_sync(
        self,
        analysis_data: List[SessionDetail],
        msg: SessionGroupMessage,
        batch_size: int,
    ):
        """Run analysis on smaller batches when a larger batch fails.

        Splits the failed batch into smaller chunks and processes each independently,
        allowing partial success if some chunks work despite memory issues in larger batches.
        """
        if len(analysis_data) <= batch_size:
            return self._run_batch_analysis_subprocess_sync(analysis_data, msg, batch_size)

        logger.info(
            "Splitting failed batch of %d into sub-batches of size %d for resilience",
            len(analysis_data),
            batch_size,
        )
        all_anomalies = []
        all_consistency = []
        all_normal_behaviour = []

        for i in range(0, len(analysis_data), batch_size):
            chunk = analysis_data[i : i + batch_size]
            end_idx = min(i + batch_size, len(analysis_data))
            logger.info(
                "Processing retry sub-batch [%d-%d] of %d with batch_size=%d",
                i,
                end_idx,
                len(analysis_data),
                batch_size,
            )
            try:
                anomalies, consistency, normal_behaviour = self._run_batch_analysis_subprocess_sync(
                    chunk, msg, batch_size
                )
                all_anomalies.extend(anomalies)
                all_consistency.extend(consistency)
                all_normal_behaviour.extend(normal_behaviour)
            except Exception as exc:
                logger.warning(
                    "Sub-batch [%d-%d] failed even at reduced batch_size=%d: %s",
                    i,
                    end_idx,
                    batch_size,
                    exc,
                )
                if batch_size > 1:
                    smaller = max(1, batch_size // 2)
                    logger.info("Re-retrying this sub-batch with batch_size=%d", smaller)
                    anomalies, consistency, normal_behaviour = self._run_batch_analysis_with_retry_sync(
                        chunk, msg, smaller
                    )
                    all_anomalies.extend(anomalies)
                    all_consistency.extend(consistency)
                    all_normal_behaviour.extend(normal_behaviour)
                else:
                    logger.error(
                        "Sub-batch [%d-%d] failed at minimum batch_size, skipping",
                        i,
                        end_idx,
                    )

        return all_anomalies, all_consistency, all_normal_behaviour

    # ------------------------------------------------------------------
    # Individual analysis jobs
    # ------------------------------------------------------------------

    async def _run_anomaly(self, analysis_data: List[SessionDetail], msg: SessionGroupMessage):
        async with self._semaphore:
            return await asyncio.to_thread(self._run_anomaly_sync, analysis_data, msg)

    def _run_anomaly_sync(self, analysis_data: List[SessionDetail], msg: SessionGroupMessage):
        persist_to_db = self.db_handler is not None and not self._skip_db_io
        if persist_to_db and not self.db_handler.analysis_pre_check(
            group_id=msg.group_id,
            report_type=AnomalyReport.__name__,
            group_hash=msg.group_hash,
            session_id=msg.session_id,
        ):
            logger.debug("Anomaly pre-check failed. Either group changed or report already exists.")
            return []

        anomalies = self.anomaly_wrapper.process_group(analysis_data)
        if not anomalies:
            logger.info("No anomaly reports generated for group %s.", msg.group_id)
            return []

        if persist_to_db:
            links_created = self.anomaly_wrapper.ingest_anomaly_report(
                self.db_handler, anomalies, msg.group_id, node_hash=msg.group_hash
            )
            if not links_created:
                logger.info("Some anomaly reports failed to attach to group %s.", msg.group_id)

        return [
            {
                "inlier_sessions": a.inlier_sessions,
                "outlier_sessions": a.outlier_sessions,
                "reason": a.reason,
                "layer": a.layer,
                "scores": a.scores,
                "metadata": a.metadata,
            }
            for a in anomalies
        ]

    async def _run_consistency(self, analysis_data: List[SessionDetail], msg: SessionGroupMessage):
        async with self._semaphore:
            return await asyncio.to_thread(self._run_consistency_sync, analysis_data, msg)

    def _run_consistency_sync(self, analysis_data: List[SessionDetail], msg: SessionGroupMessage):
        persist_to_db = self.db_handler is not None and not self._skip_db_io
        if persist_to_db and not self.db_handler.analysis_pre_check(
            group_id=msg.group_id,
            report_type=ConsistencyReport.__name__,
            group_hash=msg.group_hash,
            session_id=msg.session_id,
        ):
            logger.debug("Consistency pre-check failed. Either group changed or report already exists.")
            return []

        consistency_report = self.consistency_wrapper.process_group(analysis_data)
        if not consistency_report:
            logger.info("No consistency reports generated for group %s.", msg.group_id)
            return []

        if persist_to_db:
            links_created = self.consistency_wrapper.ingest_consistency(
                self.db_handler,
                consistency_report,
                msg.group_id,
                node_hash=msg.group_hash,
            )
            if not links_created:
                logger.info(
                    "Some consistency reports failed to attach to group %s.",
                    msg.group_id,
                )

        return [
            {
                "consistency_result": r.consistency_result.__dict__,
                "session_ids": r.session_ids,
                "layer": r.layer,
                "metadata": r.metadata,
            }
            for r in consistency_report
        ]

    async def _run_normal_behaviour(self, analysis_data: List[SessionDetail], msg: SessionGroupMessage):
        async with self._semaphore:
            return await asyncio.to_thread(self._run_normal_behaviour_sync, analysis_data, msg)

    def _run_normal_behaviour_sync(self, analysis_data: List[SessionDetail], msg: SessionGroupMessage):
        persist_to_db = self.db_handler is not None and not self._skip_db_io
        if persist_to_db and not self.db_handler.analysis_pre_check(
            group_id=msg.group_id,
            report_type=NormalBehaviourReport.__name__,
            group_hash=msg.group_hash,
            session_id=msg.session_id,
        ):
            logger.debug("Normal behaviour pre-check failed. Either group changed or report already exists.")
            return []

        reports = self.normal_behaviour_wrapper.process_group(analysis_data)
        if not reports:
            logger.info("No normal behaviour reports generated for group %s.", msg.group_id)
            return []

        if persist_to_db:
            all_ok = True
            for report in reports:
                metadata = report.metadata or {}
                raw_result = report.normal_behaviour.__dict__
                report_id = hashlib.sha256(
                    (str(msg.group_id) + str(report.layer) + str(metadata.get("metric", ""))).encode()
                ).hexdigest()
                representative_sample = report.normal_behaviour.representative_sample
                representative_processed_sample = getattr(
                    report.normal_behaviour, "representative_processed_sample", None
                )
                node = NormalBehaviourReport(
                    id=report_id,
                    dataType=report.layer,
                    rawResult=json.dumps(raw_result),
                    centroid=json.dumps(report.normal_behaviour.centroid),
                    representativeSample=json.dumps(representative_sample) if representative_sample is not None else "",
                    representativeProcessedSample=representative_processed_sample or "",
                )
                if not self.db_handler.ingest_normal_behaviour_report(
                    group_id=msg.group_id,
                    group_hash=msg.group_hash,
                    normal_behaviour_report=node,
                    source=report,
                ):
                    all_ok = False
            if not all_ok:
                logger.info(
                    "Some normal behaviour reports failed to attach to group %s.",
                    msg.group_id,
                )

        return [
            {
                "normal_behaviour": r.normal_behaviour.__dict__,
                "session_ids": r.session_ids,
                "layer": r.layer,
                "metadata": r.metadata,
            }
            for r in reports
        ]

    # ------------------------------------------------------------------
    # Main message handler
    # ------------------------------------------------------------------

    def _load_analysis_data(self, msg: SessionGroupMessage, log_context: str) -> List[SessionDetail] | None:
        if msg.sessions:
            logger.info(
                "%s [%s]: processing %d inline sessions",
                log_context,
                msg.group_id,
                len(msg.sessions),
            )
            return [SessionDetail.model_validate(s) for s in msg.sessions]

        logger.debug(
            "%s [%s]: no inline sessions, fetching in Neo4j",
            log_context,
            msg.group_id,
        )
        if not self.embedding_model:
            logger.error(
                "%s [%s]: embedding model not provided, cannot fetch from Neo4j",
                log_context,
                msg.group_id,
            )
            return None
        if self.db_handler is None:
            logger.error(
                "%s [%s]: no DB connection, cannot fetch from Neo4j",
                log_context,
                msg.group_id,
            )
            return None

        try:
            group_data = self.db_handler.get_analysis_data_for_semantic_group(
                msg.group_id,
                msg.group_hash,
                self.embedding_model,
            )
        except Exception as exc:
            logger.error(
                "%s [%s]: failed to fetch from Neo4j: %s",
                log_context,
                msg.group_id,
                exc,
            )
            return None

        if not group_data:
            logger.warning(
                "%s [%s]: no sessions found in Neo4j",
                log_context,
                msg.group_id,
            )
            return None

        return [SessionDetail.model_validate(s) for s in group_data]

    async def _analyze_message(self, msg: SessionGroupMessage, log_context: str) -> AnalysisOutputMessage | None:
        analysis_data = self._load_analysis_data(msg, log_context)
        if analysis_data is None:
            return None

        session_count = len(analysis_data)
        anomalies, consistency, normal_behaviour = await asyncio.gather(
            self._run_anomaly(analysis_data, msg),
            self._run_consistency(analysis_data, msg),
            self._run_normal_behaviour(analysis_data, msg),
        )
        del analysis_data

        return AnalysisOutputMessage(
            session_id=msg.session_id,
            group_id=msg.group_id,
            batch_index=1,
            batch_session_count=session_count,
            sessions=[],
            anomalies=anomalies or [],
            consistency=consistency or [],
            normal_behaviour=normal_behaviour or [],
        )

    async def handle_inline_message(self, msg: SessionGroupMessage) -> AnalysisOutputMessage | None:
        """Process a single inline analysis payload.

        This path is used by CLI-managed run-once mode where messages are read from
        input files (single object or array) instead of RabbitMQ.
        """
        return await self._analyze_message(msg, "handle_inline_message")

    async def handle_message(self, msg: SessionGroupMessage):
        if msg.sessions:
            try:
                output = await self._analyze_message(msg, "handle_message")
            except Exception as exc:
                logger.exception("handle_message [%s]: inline analysis failed: %s", msg.group_id, exc)
                return False
            finally:
                self._skip_db_io = False

            if output is None:
                return False

            self.output_messages = [output]
            logger.info("%s processed message for group %s", self.name, msg.group_id)
            return True
        else:
            if not self.embedding_model:
                logger.error("Embedding model not provided. Dropping message.")
                return False

            if self.db_handler is None:
                logger.warning("Connection to database is missing. Dropping message.")
                return False

            logger.info(
                "handle_message [%s]: waiting for hierarchical grouping unlock",
                msg.group_id,
            )
            if not await self.db_handler.wait_for_hierarchical_grouping_unlock():
                logger.info(
                    "Hierarchical grouping lock active, skipping analysis for group %s.",
                    msg.group_id,
                )
                return False

            output = await self._analyze_message(msg, "handle_message")

            if output is None:
                return False

            self.output_messages = [output]

            logger.info(
                "handle_message [%s]: analysis complete — total sessions: %d",
                msg.group_id,
                output.batch_session_count,
            )

            logger.info("%s processed message for group %s", self.name, msg.group_id)
            return True
