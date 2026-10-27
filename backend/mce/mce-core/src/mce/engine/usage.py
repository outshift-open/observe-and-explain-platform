#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Per-metric accounting of the LLM calls a metric makes while it is computed.

``track_usage()`` opens a scope; every ``LLMService.complete()`` call made
inside it (in this thread, or in a worker thread started with
``contextvars.copy_context()``) adds its token usage to the scope's
``JudgeUsage``. The engine opens one scope per metric computation and stamps the
result's metadata with the totals and an estimated USD cost.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from mce.engine.pricing import estimate_cost_usd


@dataclass
class JudgeUsage:
    """Token usage summed over every LLM call made inside one scope."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    models: list[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        with self._lock:
            self.prompt_tokens += int(prompt_tokens or 0)
            self.completion_tokens += int(completion_tokens or 0)
            self.calls += 1
            if model and model not in self.models:
                self.models.append(model)

    def to_metadata(self) -> dict[str, Any]:
        """Metadata keys persisted with the metric result; empty if no LLM call."""
        if not self.calls:
            return {}
        model = self.models[0] if len(self.models) == 1 else ",".join(self.models)
        metadata: dict[str, Any] = {
            "evaluation_model": model,
            "evaluation_prompt_tokens": self.prompt_tokens,
            "evaluation_completion_tokens": self.completion_tokens,
            "evaluation_total_tokens": self.total_tokens,
        }
        if len(self.models) == 1:
            cost = estimate_cost_usd(
                self.models[0], self.prompt_tokens, self.completion_tokens
            )
            if cost is not None:
                metadata["evaluation_cost_usd"] = cost
        return metadata


_current: ContextVar[JudgeUsage | None] = ContextVar("mce_judge_usage", default=None)


@contextmanager
def track_usage() -> Iterator[JudgeUsage]:
    """Collect the usage of every LLM call made inside the ``with`` block."""
    usage = JudgeUsage()
    token = _current.set(usage)
    try:
        yield usage
    finally:
        _current.reset(token)


def record_usage(model: str, prompt_tokens: int, completion_tokens: int) -> None:
    """Add one LLM call to the current scope, if there is one."""
    usage = _current.get()
    if usage is not None:
        usage.add(model, prompt_tokens, completion_tokens)
