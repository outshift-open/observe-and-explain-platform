#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

# queue for new sessions ready in the datalake and that need to be normalized
NEW_SESSION_IN_Q = "new_session_in"

# queue for sessions that have been normalized and are ready for MCE processing
NEW_SESSION_TO_MCE_Q = "new_session_to_mce"

# queue for sessions that have been normalized and are ready for embedding processing
NEW_SESSION_TO_EMB_Q = "new_session_to_embedding"
