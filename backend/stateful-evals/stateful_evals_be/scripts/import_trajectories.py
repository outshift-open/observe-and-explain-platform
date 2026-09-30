#!/usr/bin/env python3
#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""
Import trajectory datasets (TAU2/NOA) into ClickHouse.

Transforms trajectory JSONs into the otel_traces schema so they're queryable via:
    http://localhost:8080/traces/session/{session_id}

Usage:
    # Import all airline trajectories:
    python -m stateful_evals_be.scripts.import_trajectories --domain airline

    # Import first 10 retail trajectories with custom ClickHouse creds:
    python -m stateful_evals_be.scripts.import_trajectories \\
        --domain retail \\
        --trajectory-dir /path/to/retail_trajectories \\
        --max-files 10 \\
        --clickhouse-url localhost \\
        --clickhouse-password mypassword

    # Import NOA trajectories:
    python -m stateful_evals_be.scripts.import_trajectories --domain noa

    # Dry run (preview without inserting):
    python -m stateful_evals_be.scripts.import_trajectories --domain airline --dry-run
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Ensure local repo paths are importable when run as a module or script.
SCRIPT_DIR = Path(__file__).resolve().parent
STATEFUL_EVALS_BE_DIR = SCRIPT_DIR.parent
BACKEND_DIR = STATEFUL_EVALS_BE_DIR.parent
STATEFUL_EVALS_DIR = BACKEND_DIR.parent
REPO_ROOT_DIR = STATEFUL_EVALS_DIR.parent
LOCAL_TRAJECTORIES_DIR = BACKEND_DIR / "data" / "trajectories"

for path in (BACKEND_DIR, REPO_ROOT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

MCE_SRC_CANDIDATES = [
    BACKEND_DIR / "telemetry-hub" / "metrics_computation_engine" / "src",
    STATEFUL_EVALS_DIR / "telemetry-hub" / "metrics_computation_engine" / "src",
    REPO_ROOT_DIR / "telemetry-hub" / "metrics_computation_engine" / "src",
]
for mce_src in MCE_SRC_CANDIDATES:
    if mce_src.exists():
        if str(mce_src) not in sys.path:
            sys.path.insert(0, str(mce_src))
        break

from stateful_evals_be.domain.trajectory_importer import (  # noqa: E402
    import_trajectories_to_clickhouse,
    list_trajectory_json_files,
    trajectory_to_otel_rows,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("import_trajectories")

# Candidate trajectory directories per domain (first existing path is used).
DEFAULT_DIR_CANDIDATES: Dict[str, List[Path]] = {
    "airline": [
        LOCAL_TRAJECTORIES_DIR / "tau2_trajectories",
        LOCAL_TRAJECTORIES_DIR / "tau2_trajectories_airline",
    ],
    "retail": [
        LOCAL_TRAJECTORIES_DIR / "tau2_trajectories_retail",
    ],
    "telecom": [
        LOCAL_TRAJECTORIES_DIR / "tau2_trajectories_telecom",
    ],
    "noa": [
        LOCAL_TRAJECTORIES_DIR / "noa_trajectories",
        LOCAL_TRAJECTORIES_DIR / "noa_trip_planner" / "gpt35_curated",
    ],
}


def _default_clickhouse_port() -> int:
    """Pick default ClickHouse HTTP port from env with safe fallback."""
    raw = os.getenv("CLICKHOUSE_HTTP_PORT") or os.getenv("CLICKHOUSE_PORT") or "8123"
    try:
        return int(raw)
    except ValueError:
        return 8123


def resolve_default_trajectory_dir(domain: str) -> Optional[Path]:
    """Return the first existing default trajectory path for the requested domain."""
    for candidate in DEFAULT_DIR_CANDIDATES.get(domain, []):
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Import trajectory datasets (TAU2/NOA) into ClickHouse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m stateful_evals_be.scripts.import_trajectories --domain airline
    python -m stateful_evals_be.scripts.import_trajectories --domain airline --max-files 5 --dry-run
    python -m stateful_evals_be.scripts.import_trajectories --domain retail --trajectory-dir /path/to/data
    python -m stateful_evals_be.scripts.import_trajectories --domain noa
        """,
    )
    parser.add_argument(
        "--domain",
        "-d",
        required=True,
        choices=["airline", "retail", "telecom", "noa"],
        help="Domain name",
    )
    parser.add_argument(
        "--trajectory-dir",
        "-t",
        type=str,
        default=None,
        help="Path to trajectory JSON directory (defaults to standard location per domain)",
    )
    parser.add_argument(
        "--max-files",
        "-n",
        type=int,
        default=None,
        help="Max trajectory files to import (default: all)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the transformation without inserting into ClickHouse",
    )
    parser.add_argument(
        "--no-clear-domain",
        action="store_true",
        help=(
            "Do not delete existing rows for this domain before import. "
            "Default behavior is to clear and re-import cleanly."
        ),
    )
    parser.add_argument(
        "--clickhouse-url",
        type=str,
        default=os.getenv("CLICKHOUSE_URL", "localhost"),
        help="ClickHouse host (default: localhost or $CLICKHOUSE_URL)",
    )
    parser.add_argument(
        "--clickhouse-port",
        type=int,
        default=_default_clickhouse_port(),
        help=(
            "ClickHouse HTTP port (default: $CLICKHOUSE_HTTP_PORT, "
            "$CLICKHOUSE_PORT, or 8123)"
        ),
    )
    parser.add_argument(
        "--clickhouse-user",
        type=str,
        default=os.getenv("CLICKHOUSE_USERNAME", "admin"),
        help="ClickHouse user (default: admin or $CLICKHOUSE_USERNAME)",
    )
    parser.add_argument(
        "--clickhouse-password",
        type=str,
        default=os.getenv("CLICKHOUSE_PASSWORD", "admin"),
        help="ClickHouse password (default: admin or $CLICKHOUSE_PASSWORD)",
    )
    parser.add_argument(
        "--clickhouse-db",
        type=str,
        default=os.getenv("CLICKHOUSE_DB", "default"),
        help="ClickHouse database (default: default or $CLICKHOUSE_DB)",
    )
    return parser.parse_args()


def dry_run(trajectory_dir: str, domain: str, max_files: int = None):
    """Preview the import without writing to ClickHouse."""
    files = list_trajectory_json_files(trajectory_dir)
    if max_files:
        files = files[:max_files]

    print(f"\n{'=' * 70}")
    print(f"DRY RUN — {len(files)} trajectory files from {trajectory_dir}")
    print(f"Domain: {domain}")
    print(f"{'=' * 70}\n")

    total_rows = 0
    for file_path in files:
        try:
            rows, meta = trajectory_to_otel_rows(file_path, domain)
            total_rows += len(rows)

            print(f"FILE {Path(file_path).name}")
            print(f"   session_id:  {meta['session_id']}")
            print(f"   reward:      {meta['reward']}")
            print(f"   spans:       {meta['num_spans']}")

            # Show first row detail
            if rows:
                r = rows[0]
                print(f"   first span:  SpanName={r['SpanName']}")
                print(
                    f"                session.id={r['SpanAttributes'].get('session.id', 'N/A')}"
                )
                sa = r["SpanAttributes"]
                # Show a few key attributes
                for key in sorted(sa.keys())[:5]:
                    val = sa[key]
                    if len(str(val)) > 80:
                        val = str(val)[:80] + "..."
                    print(f"                {key}={val}")
            print()
        except Exception as e:
            print(f"ERROR {Path(file_path).name}: {e}\n")

    print(f"{'=' * 70}")
    print(f"Total: {len(files)} files → {total_rows} otel_traces rows")
    print("Query endpoint: http://localhost:8080/traces/session/{session_id}")
    print("")
    print("On real import, a manifest JSON will be saved to:")
    print(f"  {trajectory_dir}/import_manifest_{domain}.json")
    print(f"{'=' * 70}\n")


def main():
    args = parse_args()

    # Resolve trajectory directory
    trajectory_dir = args.trajectory_dir
    if trajectory_dir is None:
        default_dir = resolve_default_trajectory_dir(args.domain)
        if default_dir is None:
            print(
                f"ERROR no default trajectory directory found for domain '{args.domain}'."
            )
            print("Checked:")
            for candidate in DEFAULT_DIR_CANDIDATES.get(args.domain, []):
                print(f"  - {candidate}")
            print("Use --trajectory-dir to specify the path.")
            sys.exit(1)
        trajectory_dir = str(default_dir)

    if not Path(trajectory_dir).exists():
        print(f"ERROR trajectory directory not found: {trajectory_dir}")
        sys.exit(1)

    print(f"\n{'=' * 70}")
    print("Trajectory Dataset -> ClickHouse Importer")
    print(f"{'=' * 70}")
    print(f"Domain:          {args.domain}")
    print(f"Trajectory dir:  {trajectory_dir}")
    print(f"Max files:       {args.max_files or 'all'}")
    print(
        f"ClickHouse:      {args.clickhouse_user}@"
        f"{args.clickhouse_url}:{args.clickhouse_port}/{args.clickhouse_db}"
    )
    print(f"Clear existing:  {not args.no_clear_domain}")
    print(f"Dry run:         {args.dry_run}")
    print(f"{'=' * 70}\n")

    if args.dry_run:
        dry_run(trajectory_dir, args.domain, args.max_files)
        return

    result = import_trajectories_to_clickhouse(
        trajectory_dir=trajectory_dir,
        domain=args.domain,
        clickhouse_url=args.clickhouse_url,
        clickhouse_port=args.clickhouse_port,
        clickhouse_user=args.clickhouse_user,
        clickhouse_password=args.clickhouse_password,
        clickhouse_db=args.clickhouse_db,
        max_files=args.max_files,
        clear_existing_domain=not args.no_clear_domain,
    )

    print(f"\n{'=' * 70}")
    print("IMPORT COMPLETE")
    print(f"{'=' * 70}")
    print(f"Status:              {result['status']}")
    print(f"Files processed:     {result['files_processed']}")
    cleared = result.get("cleared_existing", {})
    if cleared:
        print(f"Rows cleared:        {cleared.get('rows_deleted', 0)}")
    print(f"Total spans inserted:{result.get('total_spans_inserted', 0)}")
    print(f"Session IDs created: {len(result.get('session_ids', []))}")
    if result.get("manifest_path"):
        print(f"Manifest saved to:   {result['manifest_path']}")
    print()

    # Print the session_id → source file mapping
    manifest = result.get("manifest", {})
    print(f"{'=' * 70}")
    print("SESSION ID → SOURCE FILE MAPPING")
    print(f"{'=' * 70}")
    for session_id, info in manifest.items():
        print(f"  {session_id}")
        print(f"    file:   {info['filename']}")
        print(f"    reward: {info['reward']}")
        print(f"    spans:  {info['num_spans']}")
        print(f"    url:    http://localhost:8080/traces/session/{session_id}")
        print()

    if result.get("manifest_path"):
        print(f"{'=' * 70}")
        print(f"Manifest JSON: {result['manifest_path']}")
        print(f"{'=' * 70}\n")


if __name__ == "__main__":
    main()
