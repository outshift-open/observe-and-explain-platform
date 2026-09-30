#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys

from oxp_ontology.validation import format_report, validate_bundled_ontologies


def main() -> int:
    report = validate_bundled_ontologies()
    print(format_report(report))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
