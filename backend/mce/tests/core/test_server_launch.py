#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from unittest.mock import patch
import mce.api.server


def test_server_main():
    with patch("uvicorn.run") as mock_run:
        # Mock environment variables
        with patch.dict("os.environ", {"HOST": "1.2.3.4", "PORT": "9000"}):
            mce.api.server.main()

            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert kwargs["host"] == "1.2.3.4"
            assert kwargs["port"] == 9000
