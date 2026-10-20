"""Evaluate a protocol with MCE metric plugins, listed in an MCE worker config.

The protocol's metrics are MCE plugins (a package that registers them under the
``metrics_computation_engine.plugins`` entry-point group) and the config names the ones to
run, in MCE's worker-config format::

    metrics:
      Session:
        - AccordConverged
        - ...
    cache: {read: false, write: false}

MCE's own cache is switched off so that nothing is stored on the Session: the results go to the
protocol's execution report instead.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable

from .base import Evaluation, ProtocolEvaluator

logger = logging.getLogger(__name__)


def _neo4j_uri() -> str:
    explicit = os.getenv("NEO4J_URI")
    if explicit:
        return explicit
    host = os.getenv("NEO4J_HOST")
    if not host:
        return "bolt://localhost:7687"
    if "://" in host:
        return host
    return f"bolt://{host}:{os.getenv('NEO4J_PORT', '7687')}"


def _client_config() -> Any:
    """MCE's client config for the graph the platform's connector uses (same environment)."""
    from mce.client.config import MCEClientConfig
    from worker_base.utils import resolve_neo4j_auth

    user, password = resolve_neo4j_auth()
    return MCEClientConfig(
        kg_host=_neo4j_uri(),
        kg_user=user or os.getenv("NEO4J_USERNAME"),
        kg_password=password or os.getenv("NEO4J_PASSWORD"),
        kg_database=os.getenv("NEO4J_DB") or os.getenv("NEO4J_DATABASE") or None,
    )


def _configure_llm_from_env() -> None:
    """Point MCE's LLM service at the judge model, when one is configured (LLM-judged metrics need it)."""
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("LLM_MODEL_NAME")
    base_url = os.getenv("LLM_BASE_MODEL_URL_MCE") or os.getenv("LLM_BASE_MODEL_URL")
    if not any([api_key, model, base_url]):
        return
    from mce.engine.llm import LLMService

    LLMService.configure(mode="live", api_key=api_key, model=model, base_url=base_url)


class McEvaluator(ProtocolEvaluator):
    """A protocol whose metrics are MCE plugins listed in ``config_path``."""

    def __init__(self, name: str, config_path: Path | str, *, service_factory: Callable[[], Any] | None = None):
        self.name = name
        self.config_path = Path(config_path)
        self._service_factory = service_factory
        self._service: Any = None
        self._lock = threading.Lock()  # the worker evaluates sessions on several threads

    def _get_service(self) -> Any:
        with self._lock:
            if self._service is None:
                if self._service_factory is not None:
                    self._service = self._service_factory()
                else:
                    from mce.client.worker import MCEWorkerService

                    _configure_llm_from_env()
                    self._service = MCEWorkerService(
                        config_path=self.config_path, client_config=_client_config(), cache_read=False, cache_write=False
                    )
            return self._service

    def evaluate(self, session_id: str) -> Evaluation:
        # The service's public API returns serialised results without the judge cost the
        # report needs, so the typed results are taken from its engine call.
        passed, failed = self._get_service()._compute_session_results(session_id)
        return Evaluation(passed=list(passed), failed=list(failed))
