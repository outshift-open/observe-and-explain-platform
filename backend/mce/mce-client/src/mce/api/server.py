#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import os

from dotenv import load_dotenv
import uvicorn

# Server entry point for the MCE REST API.


def main():
    load_dotenv()

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    workers = int(os.getenv("WORKERS", "1"))

    uvicorn.run(
        "mce.api.app:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        workers=workers if not reload else 1,
    )


if __name__ == "__main__":
    main()
