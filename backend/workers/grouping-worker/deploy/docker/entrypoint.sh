#!/bin/sh
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
set -eu

echo "Running workflow: ${INPUT_WORKFLOW:-}"

if [ "$#" -eq 0 ]; then
  if [ -z "${INPUT_WORKFLOW:-}" ]; then
    echo "No workflow specified. Starting worker with default CLI/env configuration."
  else
    workflow="${INPUT_WORKFLOW#\"}"
    workflow="${workflow%\"}"
    eval "set -- $workflow"
  fi
fi

input_file=""
prev_arg=""
is_test_mode="false"
for arg in "$@"; do
  echo "Argument: $arg"
  if [ "$arg" = "--test" ]; then
    is_test_mode="true"
  fi
  if [ "$prev_arg" = "--input" ]; then
    input_file="$arg"
  fi
  prev_arg="$arg"
done

echo "Parsed input file: ${input_file:-None}"

if [ -n "$input_file" ] && [ -f "$input_file" ]; then
  echo "=== Input file content: $input_file ==="
  cat "$input_file"
  echo "=== End of input file ==="
elif [ "$is_test_mode" != "true" ]; then
  echo "No input file found in arguments: $@"
fi

exec /opt/venv/bin/grouping-worker-cli "$@"
