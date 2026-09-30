# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

# Populated at build time by docker/metadata-action's bake-file output
# (see .github/workflows/reusable-docker-build-push.yml).
target "docker-metadata-action" {}

group "default" {
  targets = ["ui"]
}

target "ui" {
  inherits   = ["docker-metadata-action"]
  context    = "ui"
  dockerfile = "Dockerfile"
  platforms  = ["linux/amd64"]
}
