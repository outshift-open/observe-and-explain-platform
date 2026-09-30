#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Persist saved MetricResult JSON files through the API library.

Reads ``*_metrics.json`` files produced by ``_maybe_save_metrics_json`` and
writes them through LocalClient using the API library's NEO4J_* settings.

Usage:
    # Push all JSON files in the default metrics_out/ directory:
    python3 -m stateful_evals_be.scripts.push_metrics_to_oxp

    # Push a single file:
    python3 -m stateful_evals_be.scripts.push_metrics_to_oxp \
        --file metrics_out/my_session_metrics.json

    # Session-level metrics only, overriding the target session_id:
    python3 -m stateful_evals_be.scripts.push_metrics_to_oxp \
        --session-only \
        --session-id example-session

    # Dry run (show what would be posted without sending):
    python3 -m stateful_evals_be.scripts.push_metrics_to_oxp --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from contextlib import nullcontext
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_METRICS_DIR = "metrics_out"
PROVIDER = "stateful_evals"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Persist saved MetricResult JSON files through the API library.",
    )
    p.add_argument(
        "--metrics-dir",
        default=DEFAULT_METRICS_DIR,
        help=f"Directory containing *_metrics.json files (default: {DEFAULT_METRICS_DIR})",
    )
    p.add_argument(
        "--file",
        dest="single_file",
        default=None,
        help="Push a single JSON file instead of scanning a directory.",
    )
    p.add_argument(
        "--session-only",
        action="store_true",
        help="Push only session-level metrics (skip span-level).",
    )
    p.add_argument(
        "--session-id",
        default=None,
        help="Override the target session_id for all metrics in the file(s). "
        "All metrics (session and span) will be posted under this session.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be written without opening a database connection.",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p.parse_args()


def collect_json_files(args: argparse.Namespace) -> list[Path]:
    if args.single_file:
        p = Path(args.single_file)
        if not p.exists():
            logger.error(f"File not found: {p}")
            sys.exit(1)
        return [p]

    d = Path(args.metrics_dir)
    if not d.is_dir():
        logger.error(f"Metrics directory not found: {d}")
        sys.exit(1)

    files = sorted(d.glob("*_metrics.json"))
    if not files:
        logger.warning(f"No *_metrics.json files found in {d}")
    return files


def write_session_metrics(
    client: Any,
    session_id: str,
    metrics: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = {"metrics": metrics}

    if dry_run:
        logger.info("  [DRY RUN] session %s", session_id)
        logger.info(f"    payload: {json.dumps(payload, indent=2)}")
        return {"written": len(metrics), "errors": [], "dry_run": True}

    return client.write_session_metrics(session_id, metrics)


def write_span_metrics(
    client: Any,
    session_id: str,
    span_id: str,
    metrics: list[dict[str, Any]],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    payload = {"metrics": metrics}

    if dry_run:
        logger.info("  [DRY RUN] session %s span %s", session_id, span_id)
        logger.info(f"    payload: {json.dumps(payload, indent=2)}")
        return {"written": len(metrics), "errors": [], "dry_run": True}

    return client.write_span_metrics(session_id, span_id, metrics)


def to_write_metric(metric: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    """Map a MetricResult dict to a WriteMetricItem dict for oxp-api."""
    value = metric.get("value")
    numeric_value = float(value) if isinstance(value, (int, float)) else None

    return {
        "name": metric["metric_name"],
        "value": numeric_value,
        "provider": PROVIDER,
        "metric_id": run_id,
        "source": "StatefulEval",
        "reasoning": metric.get("reasoning") or "",
    }


def push_file(
    filepath: Path,
    client: Any,
    *,
    session_only: bool = False,
    session_id_override: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Process one *_metrics.json file and push to oxp-api."""
    logger.info(f"Processing {filepath}")
    with open(filepath) as f:
        records: list[dict[str, Any]] = json.load(f)

    if not records:
        logger.warning("  Empty file, skipping.")
        return {"session_posted": 0, "span_posted": 0, "skipped": 0, "errors": 0}

    run_id = str(uuid.uuid4())
    logger.info(f"  metric_id (run): {run_id}")

    session_batch: dict[str, list[dict[str, Any]]] = {}
    span_batch: dict[tuple[str, str], list[dict[str, Any]]] = {}
    skipped = 0

    for rec in records:
        level = rec.get("aggregation_level", "")
        session_ids = rec.get("session_id") or []
        span_ids = rec.get("span_id") or []
        sid = session_id_override or (session_ids[0] if session_ids else "")

        if not sid:
            logger.warning(
                f"  Skipping metric {rec.get('metric_name')!r}: no session_id"
            )
            skipped += 1
            continue

        wm = to_write_metric(rec, run_id=run_id)

        if level == "session":
            session_batch.setdefault(sid, []).append(wm)
        elif level == "span":
            if session_only:
                skipped += 1
                continue
            else:
                span_id = span_ids[0] if span_ids else ""
                if not span_id:
                    logger.warning(
                        f"  Skipping span metric {rec.get('metric_name')!r}: "
                        f"no span_id (session={sid})"
                    )
                    skipped += 1
                    continue
                span_batch.setdefault((sid, span_id), []).append(wm)
        else:
            logger.warning(
                f"  Skipping metric {rec.get('metric_name')!r}: "
                f"unknown aggregation_level={level!r}"
            )
            skipped += 1

    session_posted = 0
    span_posted = 0
    errors = 0

    for sid, metrics in session_batch.items():
        try:
            result = write_session_metrics(
                client,
                sid,
                metrics,
                dry_run=dry_run,
            )
            written = result.get("written", 0)
            errs = result.get("errors", [])
            session_posted += written
            if errs:
                for e in errs:
                    logger.error(f"  Session {sid}: {e}")
                errors += len(errs)
            else:
                logger.info(f"  Session {sid}: wrote {written} metric(s)")
        except Exception as exc:
            logger.error(f"  Session {sid}: database write error: {exc}")
            errors += len(metrics)

    for (sid, span_id), metrics in span_batch.items():
        try:
            result = write_span_metrics(
                client,
                sid,
                span_id,
                metrics,
                dry_run=dry_run,
            )
            written = result.get("written", 0)
            errs = result.get("errors", [])
            span_posted += written
            if errs:
                for e in errs:
                    logger.error(f"  Span {span_id}: {e}")
                errors += len(errs)
            else:
                logger.info(
                    f"  Span {span_id} (session {sid}): wrote {written} metric(s)"
                )
        except Exception as exc:
            logger.error(
                f"  Span {span_id} (session {sid}): database write error: {exc}"
            )
            errors += len(metrics)

    return {
        "session_posted": session_posted,
        "span_posted": span_posted,
        "skipped": skipped,
        "errors": errors,
    }


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    files = collect_json_files(args)
    if not files:
        return

    logger.info(f"Files to process: {len(files)}")
    if args.session_only:
        logger.info("Mode: SESSION-ONLY (all metrics posted as session-level)")
    if args.session_id:
        logger.info(f"Session ID override: {args.session_id}")
    if args.dry_run:
        logger.info("*** DRY RUN — no requests will be sent ***")

    totals = {"session_posted": 0, "span_posted": 0, "skipped": 0, "errors": 0}

    from stateful_evals_be.integrations.oxp import local_api_client

    connection = (
        nullcontext(None) if args.dry_run else local_api_client(persist_metrics=True)
    )
    with connection as client:
        for f in files:
            counts = push_file(
                f,
                client,
                session_only=args.session_only,
                session_id_override=args.session_id,
                dry_run=args.dry_run,
            )
            for k in totals:
                totals[k] += counts[k]

    logger.info("=" * 50)
    logger.info("SUMMARY")
    logger.info(f"  Files processed:        {len(files)}")
    logger.info(f"  Session metrics posted:  {totals['session_posted']}")
    logger.info(f"  Span metrics posted:     {totals['span_posted']}")
    logger.info(f"  Skipped:                 {totals['skipped']}")
    logger.info(f"  Errors:                  {totals['errors']}")
    logger.info("=" * 50)

    if totals["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
