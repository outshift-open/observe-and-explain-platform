#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Thin wrapper around :class:`~oxp.client.mock.client.GoldenClient`.

Provides module-level functions that delegate to a shared ``GoldenClient``
instance so existing tests can keep doing ``mocker.get_applications()`` etc.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging

from oxp.client.mock import GoldenClient

logger = logging.getLogger(__name__)

_SKIP_PARAMS = {"start_time", "end_time"}

# Shared singleton used by every function below.
_golden = GoldenClient()

# Shared singleton used by every function below.
_golden = GoldenClient()


def log_mocked(func):
    """Decorator that auto-logs ``── MOCKED <name> (<params>) ──`` + result."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        sig = inspect.signature(func)
        bound = sig.bind(*args, **kwargs)
        bound.apply_defaults()
        params = ", ".join(
            f"{k}={v}" for k, v in bound.arguments.items() if k not in _SKIP_PARAMS
        )
        logger.info(f"\n── MOCKED.{func.__name__} ({params}) ──")
        logger.info(f"\n── MOCKED.{func.__name__} ({params}) ──")
        logger.debug(json.dumps(result.model_dump(), indent=2))
        return result

    return wrapper


@log_mocked
def get_applications(start_time: str = "", end_time: str = ""):
    return _golden.get_applications(start_time=start_time, end_time=end_time)


@log_mocked
def get_application_names(start_time: str = "", end_time: str = ""):
    return _golden.get_application_names(start_time=start_time, end_time=end_time)


@log_mocked
def get_spans(span_id: str, start_time: str = "", end_time: str = ""):
    return _golden.get_spans(span_id=span_id, start_time=start_time, end_time=end_time)


@log_mocked
def get_session_agent_details(
    session_id: str, agent_id: str, start_time: str = "", end_time: str = ""
):
    return _golden.get_session_agent_details(
        session_id=session_id,
        agent_id=agent_id,
        start_time=start_time,
        end_time=end_time,
    )


@log_mocked
def get_application_details(
    application_id: str, start_time: str = "", end_time: str = ""
):
    return _golden.get_application_details(
        application_id=application_id,
        start_time=start_time,
        end_time=end_time,
    )


@log_mocked
def get_application_agents(
    application_id: str, start_time: str = "", end_time: str = ""
):
    return _golden.get_application_agents(
        application_id=application_id,
        start_time=start_time,
        end_time=end_time,
    )


@log_mocked
def get_application_sessions(
    application_id: str, start_time: str = "", end_time: str = ""
):
    return _golden.get_application_sessions(
        application_id=application_id,
        start_time=start_time,
        end_time=end_time,
    )


@log_mocked
def get_application_charts(
    application_id: str,
    agent_id: str,
    chart_type: str,
    start_time: str = "",
    end_time: str = "",
):
    return _golden.get_application_charts(
        application_id=application_id,
        agent_id=agent_id,
        chart_type=chart_type,
        start_time=start_time,
        end_time=end_time,
    )


@log_mocked
def get_application_topology(application_id: str):
    return _golden.get_application_topology(application_id=application_id)


@log_mocked
def _get_session_timeline(session_id: str, start_time: str = "", end_time: str = ""):
    return _golden._get_session_timeline(
        session_id=session_id,
        start_time=start_time,
        end_time=end_time,
    )
