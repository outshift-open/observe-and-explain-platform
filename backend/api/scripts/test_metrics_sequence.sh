#!/usr/bin/env bash
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

set -euo pipefail

base_url="${1:?base URL required}"
session_id="${2:?session ID required}"
metric_id="${3:?metric ID required}"
compute_metric_id="${4:?compute metric ID required}"

pause() {
  printf "\nPress Enter to continue..."
  read -r _
}

run_get() {
  local label="$1"
  local url="$2"

  echo
  echo "${label}"
  echo "curl -X GET \"${url}\""
  curl -sS -X GET "${url}"
  echo
  pause
}

run_post() {
  local label="$1"
  local url="$2"
  local body="$3"

  echo
  echo "${label}"
  echo "curl -X POST \"${url}\" -H \"Content-Type: application/json\" -d '${body}'"
  curl -sS -X POST "${url}" -H "Content-Type: application/json" -d "${body}"
  echo
  pause
}

run_get "GET /metrics/catalog" "${base_url}/api/v1/metrics/catalog"
run_get "GET /metrics/info" "${base_url}/api/v1/metrics/info?metric_id=${metric_id}"
run_get "GET /metrics/timeseries (Relative Time)" "${base_url}/api/v1/metrics/timeseries?metric_id=${metric_id}&duration=24h&bucket=hour"
run_get "GET /metrics/timeseries (Absolute Time)" "${base_url}/api/v1/metrics/timeseries?metric_id=${metric_id}&start_time=1698000000&end_time=1698604800&bucket=day"
run_get "GET /metrics/sessions/{id}" "${base_url}/api/v1/metrics/sessions/${session_id}?metric_names=Duration&metric_names=Cost&compute=true&persist=false"
run_post "POST /metrics/compute" "${base_url}/api/v1/metrics/compute" "{\"metric_id\": \"${compute_metric_id}\", \"session_ids\": [\"${session_id}\"]}"