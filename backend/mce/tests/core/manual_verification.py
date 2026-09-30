#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import sys
import os
import time
import logging
from typing import Dict, Any, Set

# Add code dir to path to find lib package
# ../../../.. is root. We want root/code.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

from lib.mce.core.engine import MetricEngine, DataProvider
from lib.mce.core.mocks import MockMetric
from lib.mce.core.base import MetricRequirements

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)


class SlowMockMetric(MockMetric):
    def compute(self, resource_id: str, context: Dict[str, Any]):
        logger.info(f"Starting {self.metric_id}")
        time.sleep(1)  # Simulate work
        logger.info(f"Finished {self.metric_id}")
        return super().compute(resource_id, context)

    def compute_batch(self, resources, contexts):
        # Simulate efficient batch processing (Constant time regardless of N)
        logger.info(f"Starting Batch {self.metric_id} (Size: {len(resources)})")
        time.sleep(1)
        logger.info(f"Finished Batch {self.metric_id}")
        # Call base compute just to generate result objects (without the sleep)
        return [super().compute(r, c) for r, c in zip(resources, contexts)]


class SimpleProvider(DataProvider):
    def get_data(self, trace_id: str, required_fields: Set[str]) -> Dict[str, Any]:
        return {"input_text": "hello", "output_text": "world"}

    # Implement Protocol fetch as well just in case
    def fetch(
        self, resource_id: str, requirements: MetricRequirements
    ) -> Dict[str, Any]:
        return {"input_text": "hello", "output_text": "world"}


def main():
    print("Initializing Engine...")
    engine = MetricEngine(max_workers=4)
    engine.set_data_provider(
        SimpleProvider()
    )  # Use set_data_provider for Registry version

    # Define Metrics
    # A (Root)
    # B (Dep A)
    # C (Dep A)
    # D (Dep B, C)

    m_a = SlowMockMetric("metric_a", "ClassA")
    m_b = SlowMockMetric("metric_b", "ClassB", dependencies=["metric_a"])
    m_c = SlowMockMetric("metric_c", "ClassC", dependencies=["metric_a"])
    m_d = SlowMockMetric("metric_d", "ClassD", dependencies=["metric_b", "metric_c"])

    # Register
    print("Registering Metrics...")
    engine.register_metric(m_a)
    engine.register_metric(m_b)
    engine.register_metric(m_c)
    engine.register_metric(m_d)

    # Verify Graph
    print("Starting Computation (Single)...")
    start_time = time.time()
    results = engine.compute_all("test_trace")
    end_time = time.time()
    duration = end_time - start_time

    print(f"\nComputation finished in {duration:.2f} seconds.")
    print(f"Results count: {len(results)}")

    if 2.9 <= duration <= 3.5:
        print("SUCCESS: Parallel execution confirmed (Approx 3s).")
    else:
        print(f"WARNING: Duration {duration:.2f}s outside expected range.")

    # Verify Batch
    print("\nStarting Computation (Batch of 2)...")
    # Should take same time ~3s if parallelized well across metrics,
    # but since ThreadPool is max_workers=4 and we have 4 metrics per item * 2 items = 8 tasks.
    # It will take longer.
    # Tasks: A1, A2, B1, B2, C1, C2, D1, D2. (A=1s, B=1s, C=1s, D=1s)
    # Gen 1: A1, A2. (2 threads). Takes 1s.
    # Gen 2: B1, B2, C1, C2. (4 threads). Takes 1s.
    # Gen 3: D1, D2. (2 threads). Takes 1s.
    # Total ~3s.

    start_time = time.time()
    results_batch = engine.compute(["trace_1", "trace_2"])
    end_time = time.time()
    duration_batch = end_time - start_time

    print(f"Batch Computation finished in {duration_batch:.2f} seconds.")
    print(f"Results keys: {results_batch.keys()}")

    if 2.9 <= duration_batch <= 3.5:
        print("SUCCESS: Batch execution parallelized correctly (Approx 3s).")
    else:
        print(f"WARNING: Batch Duration {duration_batch:.2f}s outside expected range.")

    engine.shutdown()


if __name__ == "__main__":
    main()
