#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import unittest
from mce.engine.strategies import ThreadStrategy, ProcessStrategy, HybridStrategy
from mce.core.metadata import MetricNature


def dummy_task(x):
    return x * 2


class TestStrategies(unittest.TestCase):
    def test_thread_strategy(self):
        s = ThreadStrategy(max_workers=2)
        f = s.submit(dummy_task, None, 10)
        self.assertEqual(f.result(), 20)
        s.shutdown()

    def test_process_strategy(self):
        # Process strategy in pytest can be tricky due to fork safety, but let's try
        s = ProcessStrategy(max_workers=2)
        f = s.submit(dummy_task, None, 10)
        self.assertEqual(f.result(), 20)
        s.shutdown()

    def test_hybrid_dispatch(self):
        s = HybridStrategy(max_workers=2)

        # 1. Thread Dispatch (Deterministic)
        f1 = s.submit(dummy_task, MetricNature.DETERMINISTIC, 5)
        self.assertEqual(f1.result(), 10)

        # 2. Process Dispatch (Geometric/CPU)
        f2 = s.submit(dummy_task, MetricNature.GEOMETRIC, 5)
        self.assertEqual(f2.result(), 10)

        s.shutdown()
