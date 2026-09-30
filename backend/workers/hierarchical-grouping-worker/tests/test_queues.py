#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

from hierarchical_grouping_worker import queues


def test_queue_name_constants_are_stable():
    assert queues.NEW_SESSION_TO_PERIODIC_GROUPING_Q == "new_session_to_periodic_grouping"
    assert queues.NEW_SESSION_TO_ANALYSIS_Q == "new_session_to_analysis"
