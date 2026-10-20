"""The Cognition protocol worker: detect which protocols a session used, and evaluate the ones it did."""

import asyncio
import logging
from typing import Any, Optional

from worker_base.base_worker import BaseWorker
from worker_base.queue_message import BaseQueueMessage

from cognition_protocols_worker import kg
from cognition_protocols_worker.detectors import detect
from cognition_protocols_worker.evaluators import default_registry as default_evaluators
from cognition_protocols_worker.reports import record_findings

logger = logging.getLogger(__name__)


class CognitionProtocolsWorker(BaseWorker):
    """Records which Cognition protocols a session's agents had and used, then evaluates the ones they used.

    For each session it:

    1. runs one detector per Cognition protocol over the session's spans, read from the KG (ACCORD and CONCORD are
       built in; other protocols plug in as ``cognition_protocol_detectors`` entry points);
    2. stores the protocols found enabled and those found activated in the session's
       ``CognitionProtocolReport`` (written, with empty lists, even when there are none), and, per *activated* protocol, which agents and skills had and used it in the
       protocol's ``CognitionProtocolExecutionReport`` (a protocol that was only enabled gets none);
    3. for every protocol found *activated* that has an evaluator (ACCORD's and CONCORD's are built in; others plug
       in as ``cognition_protocol_evaluators`` entry points), computes its metrics and attaches them to that
       protocol's execution report. A protocol that was only enabled is not evaluated.

    All graph access goes through the platform's providers; the worker holds no queries.
    """

    def __init__(
        self,
        rabbitmq_url: str,
        input_queue: str,
        output_queue: Optional[list[str]] = None,
        feedback_queue=None,
        message_limit: int = -1,
        max_inflight_messages: int = 4,
        reader: Any = None,
        writer: Any = None,
        detectors: Any = None,
        evaluators: Any = None,
    ):
        super().__init__(
            rabbitmq_url=rabbitmq_url,
            input_queue=input_queue,
            output_queue=output_queue or [],
            feedback_queue=feedback_queue,
            message_limit=message_limit,
            max_inflight_messages=max_inflight_messages,
        )
        self.name = "CognitionProtocolsWorker"
        self.input_message_class = BaseQueueMessage
        self._reader = reader
        self._writer = writer
        # Detectors: None means every registered one. Evaluators: protocol name -> evaluator.
        self._detectors = detectors
        self._evaluators = evaluators

    def _get_reader(self):
        if self._reader is None:
            self._reader = kg.reader()
        return self._reader

    def _get_writer(self):
        if self._writer is None:
            self._writer = kg.writer()
        return self._writer

    def _get_evaluators(self) -> dict[str, Any]:
        if self._evaluators is None:
            self._evaluators = {e.name: e for e in default_evaluators().evaluators()}
        elif not isinstance(self._evaluators, dict):
            self._evaluators = {e.name: e for e in self._evaluators}
        return self._evaluators

    def _evaluate(self, session_id: str, protocol: str, evaluator: Any) -> bool:
        """Compute a protocol's metrics and attach them to its execution report; False on failure."""
        try:
            evaluation = evaluator.evaluate(session_id)
        except Exception:
            logger.exception("[%s] evaluating %s failed", session_id[:8], protocol)
            return False
        if not self._get_writer().save_protocol_execution_metrics(session_id, protocol, evaluation.passed):
            return False
        logger.info("[%s] %s: %d metrics stored (%d skipped)", session_id[:8], protocol, len(evaluation.passed), len(evaluation.failed))
        return True

    def _process(self, session_id: str) -> bool | None:
        findings = detect(kg.fetch_session(self._get_reader(), session_id), self._detectors)
        logger.info(
            "[%s] protocols enabled=%s activated=%s",
            session_id[:8],
            [n for n, f in findings.items() if f.enabled],
            [n for n, f in findings.items() if f.activated],
        )
        if not record_findings(self._get_writer(), session_id, findings):
            logger.warning("[%s] session not in the graph, nothing written", session_id[:8])
            return None

        evaluators = self._get_evaluators()
        ok = True
        for protocol, finding in findings.items():
            if finding.activated and protocol in evaluators:
                ok = self._evaluate(session_id, protocol, evaluators[protocol]) and ok
        return True if ok else None

    async def handle_message(self, msg: BaseQueueMessage):
        # None tells the base worker the message failed; the blocking KG and MCE calls run off the event loop.
        return await asyncio.to_thread(self._process, msg.session_id)
