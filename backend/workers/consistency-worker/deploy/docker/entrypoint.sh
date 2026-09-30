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
config_file=""
prev_arg=""
for arg in "$@"; do
  echo "Argument: $arg"
  if [ "$prev_arg" = "--input" ]; then
    input_file="$arg"
  fi
  if [ "$prev_arg" = "--config-file" ] || [ "$prev_arg" = "--config_file" ]; then
    config_file="$arg"
  fi
  prev_arg="$arg"
done

echo "Parsed input file: ${input_file:-None}"
echo "Parsed config file: ${config_file:-None}"

if [ -n "$input_file" ] && [ -f "$input_file" ]; then
  echo "=== Input file content: $input_file ==="
  cat "$input_file"
  echo "=== End of input file ==="
else
  echo "No input file found in arguments: $@"
fi

if [ -n "$config_file" ] && [ -f "$config_file" ]; then
  echo "=== Config file content: $config_file ==="
  cat "$config_file"
  echo "=== End of config file ==="
fi

exec /opt/venv/bin/consistency-worker-cli "$@"
