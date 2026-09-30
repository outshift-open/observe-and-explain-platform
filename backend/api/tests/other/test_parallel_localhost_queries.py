#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Simple smoke test to call two localhost endpoints in parallel.

Run with output visible:
    pytest tests/other/test_parallel_localhost_queries.py -s -q
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import pytest

URLS = [
    "http://localhost:8000/api/v1/applications/noa-trip-planner-mas?start_time=1767285027&end_time=1788091400",
    "http://localhost:8000/api/v1/agentic-protocols-metrics?application=noa-trip-planner-mas",
]


def _truncate(value: str, max_chars: int = 1500) -> str:
    if len(value) <= max_chars:
        return value
    return value[:max_chars] + "... <truncated>"


def _fetch(url: str) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        with urllib_request.urlopen(url, timeout=30) as response:  # nosec B310
            status_code = response.getcode()
            raw_body = response.read().decode("utf-8", errors="replace")
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        try:
            body: Any = json.loads(raw_body)
        except ValueError:
            body = _truncate(raw_body)

        return {
            "url": url,
            "status_code": status_code,
            "ok": 200 <= status_code < 300,
            "elapsed_ms": elapsed_ms,
            "body": body,
        }
    except urllib_error.HTTPError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        error_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            parsed_error_body: Any = json.loads(error_body)
        except ValueError:
            parsed_error_body = _truncate(error_body)
        return {
            "url": url,
            "status_code": exc.code,
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "body": parsed_error_body,
            "error": str(exc),
        }
    except urllib_error.URLError as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        return {
            "url": url,
            "error": str(exc),
            "elapsed_ms": elapsed_ms,
        }


def test_parallel_localhost_queries_show_results() -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_fetch, URLS))

    print("\n=== Parallel query results ===")
    for result in results:
        print(json.dumps(result, indent=2, default=str))

    if all("error" in result for result in results):
        pytest.skip(
            "Could not reach localhost:8000 for either request. "
            "Start the API server and re-run this test."
        )

    assert len(results) == 2
    assert all(("status_code" in result) or ("error" in result) for result in results)
