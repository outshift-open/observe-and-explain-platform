#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
from typing import Protocol
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future

# Optional is used for the lazy process_executor type hint
import asyncio
import multiprocessing
import logging
from mce.core.metric import MetricNature

logger = logging.getLogger(__name__)


class ExecutionStrategy(Protocol):
    """Pluggable execution strategy interface."""

    def submit(self, fn, nature: MetricNature | None, *args, **kwargs) -> Future: ...
    def shutdown(self, wait=True): ...


class ThreadStrategy:
    def __init__(self, max_workers=None):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn, nature, *args, **kwargs):
        # Ignore nature, always thread
        return self.executor.submit(fn, *args, **kwargs)

    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait)


class ProcessStrategy:
    def __init__(self, max_workers=None):
        self.executor = ProcessPoolExecutor(max_workers=max_workers)

    def submit(self, fn, nature, *args, **kwargs):
        # Ignore nature, always process
        return self.executor.submit(fn, *args, **kwargs)

    def shutdown(self, wait=True):
        self.executor.shutdown(wait=wait)


class HybridStrategy:
    """Dispatches between Threads (I/O) and Processes (CPU).

    The ProcessPoolExecutor is created lazily on first CPU-bound dispatch to
    avoid spawning processes in test environments where no such work is done.
    """

    def __init__(self, max_workers=None):
        self.thread_executor = ThreadPoolExecutor(max_workers=max_workers)
        self._max_workers = max_workers
        self._process_executor: ProcessPoolExecutor | None = None

    @property
    def process_executor(self) -> ProcessPoolExecutor:
        if self._process_executor is None:
            proc_workers = max(
                1, (self._max_workers or multiprocessing.cpu_count()) // 2
            )
            self._process_executor = ProcessPoolExecutor(max_workers=proc_workers)
        return self._process_executor

    def submit(self, fn, nature: MetricNature | None, *args, **kwargs):
        # Dispatch logic: CPU intensive? -> Process; I/O waiting? -> Thread
        if nature in [MetricNature.GEOMETRIC, MetricNature.TOPOLOGICAL]:
            return self.process_executor.submit(fn, *args, **kwargs)
        else:
            # DETERMINISTIC, STOCHASTIC (LLMs), etc.
            return self.thread_executor.submit(fn, *args, **kwargs)

    def shutdown(self, wait=True):
        self.thread_executor.shutdown(wait=wait)
        if self._process_executor is not None:
            self._process_executor.shutdown(wait=wait)


class AsyncIOStrategy:
    """
    Executes tasks in an asyncio event loop.
    Best for valid async metrics (awaitable).
    """

    def __init__(self, loop=None):
        # asyncio.get_event_loop() is deprecated in Python 3.10 and raises
        # DeprecationWarning / RuntimeError in 3.12 when there is no running loop.
        # Always create a fresh loop to stay compatible.
        if loop is not None:
            self.loop = loop
        else:
            self.loop = asyncio.new_event_loop()
            # Fix #9: do NOT call asyncio.set_event_loop() — it clobbers any loop
            # already set on this thread (e.g. in test environments or async frameworks).

    def submit(self, fn, nature, *args, **kwargs):
        # Wraps the synchronous fn in run_in_executor to not block the loop
        # Returns an asyncio.Future wrapped as concurrent.futures.Future
        concurrent_future: Future = Future()

        async def run():
            try:
                res = await self.loop.run_in_executor(None, fn, *args, **kwargs)
                concurrent_future.set_result(res)
            except Exception as e:
                concurrent_future.set_exception(e)

        # Fix #4: guard against the loop not running / being closed before the
        # coroutine is scheduled — in that case the future would never be resolved
        # and future.result() in the engine would block forever.
        try:
            asyncio.run_coroutine_threadsafe(run(), self.loop)
        except Exception as e:
            concurrent_future.set_exception(e)
        return concurrent_future

    def shutdown(self, wait: bool = True):
        """Request the event loop to stop; optionally wait for pending tasks."""
        if wait:
            pending = asyncio.all_tasks(self.loop)
            if pending:
                self.loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        self.loop.stop()
        self.loop.close()
