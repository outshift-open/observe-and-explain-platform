#!/bin/sh
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

set -ex
env
envsubst '$VITE_API_PROXY_URL $VITE_REST_API_URL $VITE_FF_SEMANTIC_GROUPS $VITE_FF_INSIGHTS $VITE_FF_LIVE_TOPOLOGY $VITE_FF_STATEFUL_EVAL $VITE_FF_IMPACT_ASSESSMENT $VITE_FF_WASTE_ESTIMATION $VITE_FF_NEUROSYMBOLIC_EVAL $VITE_FF_COGNITIVE_OBSERVABILITY $VITE_FF_L9_PROTOCOLS' < /app/nginx.conf.template > /etc/nginx/conf.d/default.conf
cat /etc/nginx/conf.d/default.conf
exec "$@"
