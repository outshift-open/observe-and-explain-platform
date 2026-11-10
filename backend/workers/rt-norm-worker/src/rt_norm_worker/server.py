#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OTLP/HTTP receiver: the OTel collector pushes spans and logs here, one request at a time.

Point the collector's ``otlphttp`` exporter at it with ``encoding: json``::

    exporters:
      otlphttp/rt-norm:
        endpoint: http://rt-norm-worker:4318
        encoding: json

Only ``POST /v1/traces`` and ``POST /v1/logs`` are served, and only OTLP/JSON (optionally
gzip-compressed). Every span / log record of a request is normalized, in order, into the graph.
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from norm import Kind

from rt_norm_worker import otlp
from rt_norm_worker.worker import Graph, process_record

logger = logging.getLogger(__name__)

_ROUTES: dict[str, tuple[Kind, Any]] = {
    "/v1/traces": ("span", otlp.spans),
    "/v1/logs": ("event", otlp.logs),
}


def make_server(graph: Graph, host: str = "0.0.0.0", port: int = 4318) -> ThreadingHTTPServer:
    # Records are normalized against the graph as stored, so two requests must not interleave.
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: dict[str, Any] | None = None) -> None:
            payload = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # health check
            self._reply(200 if self.path in ("/", "/healthz") else 404)

        def do_POST(self) -> None:
            route = _ROUTES.get(self.path.split("?")[0])
            if route is None:
                return self._reply(404, {"error": f"unknown path {self.path}"})
            if "json" not in self.headers.get("Content-Type", ""):
                return self._reply(
                    415, {"error": "only OTLP/JSON is supported: set `encoding: json` on the exporter"}
                )
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                if self.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                request = json.loads(body or b"{}")
            except (OSError, ValueError) as error:
                return self._reply(400, {"error": f"invalid request: {error}"})

            kind, flatten = route
            try:
                with lock:
                    for record in flatten(request):
                        process_record(graph, record, kind)
            except Exception:  # the collector retries on 5xx
                logger.exception("failed to normalize %s request", kind)
                return self._reply(500, {"error": "normalization failed"})
            self._reply(200)

        def log_message(self, format: str, *args: Any) -> None:
            logger.debug(format, *args)

    return ThreadingHTTPServer((host, port), Handler)


def serve(graph: Graph, host: str = "0.0.0.0", port: int = 4318) -> None:
    server = make_server(graph, host, port)
    logger.info("rt-norm-worker listening on %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
