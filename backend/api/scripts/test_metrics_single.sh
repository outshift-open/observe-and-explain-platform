#!/usr/bin/env bash
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

set -euo pipefail

base_url="${1:?base URL required}"
session_id="${2:?session ID required}"
metric_a="${3:?first metric name required}"
metric_b="${4:?second metric name required}"

echo "GET ${base_url}/api/v1/metrics/sessions/${session_id}"
url="${base_url}/api/v1/metrics/sessions/${session_id}?metric_names=${metric_a}&metric_names=${metric_b}&compute=true&persist=false"
echo "curl -X GET \"${url}\""
response="$(curl -sS -X GET "${url}")"
printf '%s\n' "${response}"

echo
echo "Filtered metrics via jq"
echo "curl -sS -X GET \"${url}\" | jq --arg metric_a \"${metric_a}\" --arg metric_b \"${metric_b}\" '.metrics | map(select(.name == \$metric_a or .name == \$metric_b or .metric_id == \$metric_a or .metric_id == \$metric_b))'"
curl -sS -X GET "${url}" | jq --arg metric_a "${metric_a}" --arg metric_b "${metric_b}" '.metrics | map(select(.name == $metric_a or .name == $metric_b or .metric_id == $metric_a or .metric_id == $metric_b))'

python3 -c '
import json
import sys

payload = json.loads(sys.argv[1])
expected = {sys.argv[2], sys.argv[3]}
present = {item.get("name") for item in payload.get("metrics", [])}
missing = sorted(expected - present)
print({"expected": sorted(expected), "present": sorted(present)})
if missing:
    raise SystemExit("missing expected metrics: " + ", ".join(missing))
' "${response}" "${metric_a}" "${metric_b}"
echo