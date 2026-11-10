#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Call the rules' callback URLs for the log records that match them."""

from __future__ import annotations

import json
import logging
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from rt_norm_worker.rules import Rule, RuleSet

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5


def post_json(url: str, payload: dict[str, Any]) -> None:
    """POST the payload as JSON. Raises on a connection error or a non-2xx answer."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS):
        pass


class Notifier:
    """After a log record is normalized, POST it to the callback URL of every rule it matches.

    The body is ``{"rule": name, "value": value, "event": <the log record>}``. Calls run on
    a small thread pool, so a slow or dead URL never holds up normalization; a failure is
    logged and not retried. ``post`` is replaceable (tests pass a recorder; ``wait=True``
    makes the calls synchronous).
    """

    def __init__(
        self,
        rules: RuleSet,
        post: Callable[[str, dict[str, Any]], None] = post_json,
        wait: bool = False,
        workers: int = 4,
    ) -> None:
        self.rules = rules
        self._post = post
        self._wait = wait
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rt-norm-callback")

    def matching(self, record: dict[str, Any]) -> list[Rule]:
        return [rule for rule in self.rules if rule.matches(record)]

    def notify(self, record: dict[str, Any]) -> list[Rule]:
        """Call back for every rule the record matches. Returns those rules."""
        matched = self.matching(record)
        for rule in matched:
            payload = {"rule": rule.name, "value": rule.value, "event": record}
            if self._wait:
                self._call(rule, payload)
            else:
                self._pool.submit(self._call, rule, payload)
        return matched

    def _call(self, rule: Rule, payload: dict[str, Any]) -> None:
        try:
            self._post(rule.callback_url, payload)
        except Exception as error:
            logger.warning("callback of rule %s to %s failed: %s", rule.key, rule.callback_url, error)

    def close(self) -> None:
        self._pool.shutdown(wait=True)
