#!/bin/sh
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
set -eu

echo "Running workflow: ${INPUT_WORKFLOW:-}"

# Prefer explicit container args; fallback to INPUT_WORKFLOW only when no args are provided.
if [ "$#" -eq 0 ]; then
  if [ -z "${INPUT_WORKFLOW:-}" ]; then
    echo "No workflow specified. Starting worker with default CLI/env configuration."
  else
    # Handle cases where INPUT_WORKFLOW is wrapped in quotes in .env.
    workflow="${INPUT_WORKFLOW#\"}"
    workflow="${workflow%\"}"
    eval "set -- $workflow"
  fi
fi

input_file=""
prev_arg=""
for arg in "$@"; do
  echo "Argument: $arg"
  if [ "$prev_arg" = "--input" ]; then
    input_file="$arg"
    break
  fi
  prev_arg="$arg"
done

echo "Parsed input file: ${input_file:-None}"

# Print input file content if it exists
if [ -n "$input_file" ] && [ -f "$input_file" ]; then
  echo "=== Input file content: $input_file ==="
  cat "$input_file"
  echo "=== End of input file ==="
else
  echo "No input file found in arguments: $@"
fi

exec /opt/venv/bin/norm-worker-cli "$@"