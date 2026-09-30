#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Backward-compatibility shim — canonical location is ``mce.client.worker``.

All logic (WorkerConfig, MCEWorkerService) lives in the ``mce-client`` package.
This module re-exports both classes so that existing callers importing from
``mce.engine.worker`` continue to work without modification.
"""

from mce.client.worker import MCEWorkerService, WorkerConfig  # noqa: F401

__all__ = ["WorkerConfig", "MCEWorkerService"]
