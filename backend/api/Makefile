#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
.PHONY: test-rest-api

test-rest-api:
	@.venv/bin/uvicorn main:app --reload & \
	sleep 3 && \
	echo "--- Applications (SQLite) ---" && \
	curl -s http://127.0.0.1:8000/applications/001 | .venv/bin/python -m json.tool && \
	echo "--- Users (ClickHouse) ---" && \
	curl -s http://127.0.0.1:8000/users/001 | .venv/bin/python -m json.tool && \
	echo "--- Favorites (PostgreSQL) ---" && \
	curl -s http://127.0.0.1:8000/users/001/favorites | .venv/bin/python -m json.tool; \
	kill %1 2>/dev/null
