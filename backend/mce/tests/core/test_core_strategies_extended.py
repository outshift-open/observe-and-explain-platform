#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import pytest
from mce.engine.strategies import (
    ProcessStrategy,
    AsyncIOStrategy,
    HybridStrategy,
    ThreadStrategy,
)
from mce.core.metadata import MetricNature
import asyncio


def dummy_task(x):
    return x * 2


def dummy_task_cpu(x):
    # Simulate CPU work
    return x + 1


@pytest.mark.timeout(5)
def test_process_strategy():
    strat = ProcessStrategy(max_workers=1)
    future = strat.submit(dummy_task, MetricNature.DETERMINISTIC, 10)
    assert future.result() == 20
    strat.shutdown()


def test_hybrid_strategy_dispatch():
    strat = HybridStrategy(max_workers=2)

    # Test Thread path
    f1 = strat.submit(dummy_task, MetricNature.DETERMINISTIC, 10)
    assert f1.result() == 20

    # Test Process path (Geometric)
    f2 = strat.submit(dummy_task_cpu, MetricNature.GEOMETRIC, 10)
    assert f2.result() == 11

    strat.shutdown()


def test_asyncio_strategy():
    async def run_test():
        loop = asyncio.get_running_loop()
        strat = AsyncIOStrategy(loop=loop)

        future = strat.submit(dummy_task, MetricNature.DETERMINISTIC, 21)

        # Poll for completion
        for _ in range(50):
            if future.done():
                break
            await asyncio.sleep(0.01)

        return future.result()

    res = asyncio.run(run_test())
    assert res == 42


def test_thread_strategy_explicit():
    strat = ThreadStrategy(max_workers=1)
    future = strat.submit(dummy_task, MetricNature.TOPOLOGICAL, 5)  # Nature ignored
    assert future.result() == 10
    strat.shutdown()
