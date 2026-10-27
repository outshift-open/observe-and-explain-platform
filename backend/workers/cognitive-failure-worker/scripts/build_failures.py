#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Regenerate ``data/failures.json`` from the challenges taxonomy.

The worker ships only what it needs to recognise a failure: code, name, locus, cognitive
function, summary, failure signature and detection heuristic. Run it again when the taxonomy
changes::

    build_failures.py PATH/TO/challenges-taxonomy.md
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src" / "cognitive_failure_worker" / "data" / "failures.json"


def _label(name: str) -> str:
    """A field label, with or without bold: ``**Name:**`` or ``Name:``."""
    return rf"^(?:\*\*)?{re.escape(name)}:(?:\*\*)?"


def _field(section: str, name: str) -> str:
    match = re.search(_label(name) + r"[ \t]*(.+)$", section, re.M)
    return match.group(1).strip() if match else ""


def _block(section: str, name: str, *, one_paragraph: bool = False) -> str:
    """Text after the ``name`` label: one paragraph, or up to the next blank line followed by another label."""
    end = r"(?=\n\s*\n)" if one_paragraph else r"(?=\n\s*\n(?:\*\*)?[A-Z][A-Za-z() -]*:|\n#{2,} |\n---|\Z)"
    match = re.search(_label(name) + r"[ \t]*\n?(.*?)" + end, section, re.M | re.S)
    return match.group(1).strip() if match else ""


def _items(block: str) -> list[str]:
    """Bullets of a block, or its lines when it is not a bullet list."""
    bullets = re.split(r"(?m)^- ", block)[1:]
    parts = bullets or [line for line in block.split("\n") if line.strip()]
    return [re.sub(r"\s+", " ", part).strip() for part in parts]


def parse(taxonomy: str) -> list[dict]:
    failures = []
    for section in re.split(r"(?m)^### ", taxonomy)[1:]:
        heading = section.split("\n", 1)[0]
        code, _, name = heading.partition(" — ")
        if not re.fullmatch(r"[A-Z]{2}-\d+", code.strip()):
            continue
        failures.append(
            {
                "code": code.strip(),
                "name": name.strip(),
                "locus": _field(section, "Locus"),
                "function": _field(section, "Cognitive Function"),
                "summary": _field(section, "Summary"),
                "signature": _items(_block(section, "Failure Signature")),
                "heuristic": re.sub(r"\s+", " ", _block(section, "Detection Heuristic", one_paragraph=True)),
            }
        )
    return failures


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    failures = parse(Path(sys.argv[1]).read_text(encoding="utf-8"))
    missing = [c["code"] for c in failures if not (c["summary"] and c["signature"] and c["heuristic"])]
    OUT.write_text(json.dumps({"failures": failures}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(failures)} failures written to {OUT}")
    if missing:
        print(f"incomplete (no summary, signature or heuristic): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
