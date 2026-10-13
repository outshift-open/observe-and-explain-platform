#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Refresh the vendored LLM price table from LiteLLM.

LiteLLM publishes ``model_prices_and_context_window.json``; this repo vendors a
copy for estimating LLM costs offline. It is written in two forms:

* the full file, used by stateful-evals (``cost_estimator.py``), and
* a trimmed copy for the MCE (``mce.engine.pricing``): input/output cost per
  token and aliases of every model that has both, nothing else.

Both are rewritten deterministically (sorted keys). Nothing is written if the
download fails validation, so a failed run leaves the copies it was given as
they were.

The Dockerfiles of the images that price LLM calls run this on every build, on
the copy installed in the image. Run it by hand to bring the copies committed in
the repo up to date.

    update_model_prices.py [--source URL_OR_PATH] [--full-file PATH] [--trimmed-file PATH]

With no ``--full-file``/``--trimmed-file``, both repo copies are refreshed;
with either, only the given ones.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL_FILE = (
    ROOT / "stateful-evals/stateful_evals_be/data/model_prices_and_context_window.json"
)
TRIMMED_FILE = ROOT / "mce/mce-core/src/mce/engine/data/model_prices.json"
DEFAULT_SOURCE = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"

# Models the cost estimators price by default or document; a download without
# them is almost certainly broken.
REQUIRED_MODELS = ("gpt-4o", "gpt-4o-mini")
MIN_ENTRIES = 1000


def load(source: str) -> dict:
    if source.startswith(("http://", "https://")):
        request = urllib.request.Request(
            source, headers={"User-Agent": "oxp-model-prices-updater"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def _priced(meta: object) -> bool:
    return (
        isinstance(meta, dict)
        and isinstance(meta.get("input_cost_per_token"), (int, float))
        and isinstance(meta.get("output_cost_per_token"), (int, float))
    )


def validate(prices: object) -> dict:
    """Raise ``ValueError`` unless ``prices`` looks like the LiteLLM price table."""
    if not isinstance(prices, dict):
        raise ValueError("the price file is not a JSON object")
    if len(prices) < MIN_ENTRIES:
        raise ValueError(
            f"only {len(prices)} entries (expected at least {MIN_ENTRIES})"
        )
    for model in REQUIRED_MODELS:
        if not _priced(prices.get(model)):
            raise ValueError(f"no per-token price for required model {model!r}")
    return prices


def trim(prices: dict) -> dict:
    """The MCE copy: per-token prices and aliases of every priced model."""
    trimmed = {}
    for name, meta in prices.items():
        if name == "sample_spec" or not _priced(meta):
            continue
        entry = {
            "input_cost_per_token": float(meta["input_cost_per_token"]),
            "output_cost_per_token": float(meta["output_cost_per_token"]),
        }
        aliases = [a for a in meta.get("aliases") or [] if isinstance(a, str)]
        if aliases:
            entry["aliases"] = aliases
        trimmed[name] = entry
    return trimmed


def render_full(prices: dict) -> str:
    return json.dumps(prices, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def render_trimmed(prices: dict) -> str:
    return json.dumps(trim(prices), separators=(",", ":"), sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help="URL or local path of the LiteLLM price file",
    )
    parser.add_argument("--full-file", type=Path, help="path of the full copy to write")
    parser.add_argument(
        "--trimmed-file", type=Path, help="path of the trimmed (MCE) copy to write"
    )
    args = parser.parse_args()

    if args.full_file is None and args.trimmed_file is None:
        args.full_file, args.trimmed_file = FULL_FILE, TRIMMED_FILE

    try:
        new = validate(load(args.source))
    except (OSError, ValueError) as exc:
        print(f"refusing to update: {exc}", file=sys.stderr)
        return 1

    outputs = []
    if args.full_file is not None:
        outputs.append((args.full_file, render_full(new)))
    if args.trimmed_file is not None:
        outputs.append((args.trimmed_file, render_trimmed(new)))

    for path, content in outputs:
        before = path.read_text(encoding="utf-8") if path.exists() else None
        if before == content:
            print(f"{path}: already up to date ({len(new)} models upstream)")
            continue
        path.write_text(content, encoding="utf-8")
        print(f"{path}: updated ({len(new)} models upstream)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
