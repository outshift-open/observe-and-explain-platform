#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import sys


# Prevent heavy ML library imports during pytest discovery
def pytest_configure(config):
    """Configure pytest to skip problematic plugin loading."""
    # Prevent opik pytest plugin from loading
    sys.modules["opik.pytest_plugin"] = None
