#!/usr/bin/env python3
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
# SPDX-License-Identifier: Apache-2.0

"""
Multi-component versioning script for oxp-ontology.

Each ontology component has its own version tracked in:
  - owl:versionInfo in the TTL file  (authoritative source of truth)
  - VERSION manifest file            (one component=version per line)
  - pyproject.toml                   (tracks 'mas' component version)

Components: mas, semantic, metrics, analysis, insight

For RC versions: Adds commit SHA as local version identifier (PEP 440)
For final releases: Clean version without metadata

Usage:
  python scripts/version_manager.py get [component]           # Get version(s)
  python scripts/version_manager.py get-full [component]      # With SHA if RC
  python scripts/version_manager.py bump <type> [component]   # Bump version(s)
  python scripts/version_manager.py set <version> [component] # Set version(s)

  component: mas | semantic | metrics | analysis | insight | all  (default: mas for get/get-full, all for bump/set)
  type:      rc | patch | minor | major

Examples:
  python scripts/version_manager.py get                 # mas version (used by CI)
  python scripts/version_manager.py get all             # all component versions
  python scripts/version_manager.py get-full            # mas version with SHA if RC
  python scripts/version_manager.py bump rc             # bump RC for all components
  python scripts/version_manager.py bump minor semantic # bump only semantic minor
  python scripts/version_manager.py set 1.2.0 all       # set all components to 1.2.0
  python scripts/version_manager.py set 1.2.0 mas       # set only mas to 1.2.0
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
VERSION_FILE = ROOT / "VERSION"
PYPROJECT_FILE = ROOT / "pyproject.toml"

# Component name → TTL file path
COMPONENTS: dict[str, Path] = {
    "mas": ROOT / "src/oxp_ontology/mas-ontology.ttl",
    "semantic": ROOT / "src/oxp_ontology/semantic-ontology.ttl",
    "metrics": ROOT / "src/oxp_ontology/metrics-ontology.ttl",
    "analysis": ROOT / "src/oxp_ontology/analysis-ontology.ttl",
    "insight": ROOT / "src/oxp_ontology/insight-ontology.ttl",
}

VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-(rc\d+))?$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_git_commit_sha(short: bool = True) -> str | None:
    """Get current git commit SHA."""
    try:
        cmd = ["git", "rev-parse", "--short=7" if short else "HEAD", "HEAD"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def parse_version(version_str: str) -> dict:
    """Parse version string into components dict."""
    match = VERSION_RE.match(version_str)
    if not match:
        raise ValueError(
            f"Invalid version format: {version_str!r}  (expected X.Y.Z or X.Y.Z-rcN)"
        )
    major, minor, patch, prerelease = match.groups()
    return {
        "major": int(major),
        "minor": int(minor),
        "patch": int(patch),
        "prerelease": prerelease,  # e.g. "rc0" or None
    }


def format_version(c: dict) -> str:
    """Format version components back to string."""
    base = f"{c['major']}.{c['minor']}.{c['patch']}"
    return f"{base}-{c['prerelease']}" if c["prerelease"] else base


def _resolve_components(component: str) -> list[str]:
    if component == "all":
        return list(COMPONENTS)
    if component not in COMPONENTS:
        raise ValueError(
            f"Unknown component {component!r}. Valid: {', '.join(COMPONENTS)} | all"
        )
    return [component]


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def read_ttl_version(component: str) -> str:
    """Read owl:versionInfo from the component's TTL file (authoritative)."""
    path = COMPONENTS[component]
    for line in path.read_text().splitlines():
        m = re.search(r'owl:versionInfo\s+"([^"]+)"', line)
        if m:
            return m.group(1)
    raise ValueError(f"owl:versionInfo not found in {path}")


def write_ttl_version(component: str, version: str) -> None:
    """Update owl:versionInfo in-place in the component's TTL file."""
    path = COMPONENTS[component]
    content = path.read_text()
    updated = re.sub(
        r'(owl:versionInfo\s+")[^"]+(")',
        rf"\g<1>{version}\2",
        content,
        count=1,
    )
    if updated == content:
        raise ValueError(f"Could not find owl:versionInfo to update in {path}")
    path.write_text(updated)


def read_version_manifest() -> dict[str, str]:
    """Read VERSION manifest → {component: version}. Falls back to TTL if file missing."""
    if not VERSION_FILE.exists():
        return {c: read_ttl_version(c) for c in COMPONENTS}
    result: dict[str, str] = {}
    for line in VERSION_FILE.read_text().splitlines():
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            key, _, val = line.partition("=")
            result[key.strip()] = val.strip()
    # Fill any missing components from TTL
    for c in COMPONENTS:
        if c not in result:
            result[c] = read_ttl_version(c)
    return result


def write_version_manifest(versions: dict[str, str]) -> None:
    """Write VERSION manifest from {component: version} dict."""
    lines = [f"{c}={versions[c]}" for c in COMPONENTS if c in versions]
    VERSION_FILE.write_text("\n".join(lines) + "\n")


def _write_pyproject_version(version: str) -> None:
    """Update version = \"...\" in pyproject.toml (first occurrence)."""
    content = PYPROJECT_FILE.read_text()
    updated = re.sub(r'version = "[^"]+"', f'version = "{version}"', content, count=1)
    PYPROJECT_FILE.write_text(updated)


def write_version(component: str, version: str) -> None:
    """Update TTL + VERSION manifest + pyproject.toml (mas only)."""
    write_ttl_version(component, version)
    manifest = read_version_manifest()
    manifest[component] = version
    write_version_manifest(manifest)
    if component == "mas":
        _write_pyproject_version(version)
    print(f"  ✅ {component}: {version}  ({COMPONENTS[component].name})")


# ---------------------------------------------------------------------------
# Public API (used by CI / other scripts)
# ---------------------------------------------------------------------------


def read_version(component: str = "mas") -> str:
    """Read version for a single component from its TTL file."""
    return read_ttl_version(component)


def get_version_with_metadata(component: str = "mas") -> str:
    """Return version; append +gSHA for RC builds (PEP 440 local identifier)."""
    version = read_ttl_version(component)
    c = parse_version(version)
    if c["prerelease"]:
        sha = get_git_commit_sha()
        if sha:
            return f"{version}+g{sha}"
    return version


def bump_version(bump_type: str, component: str = "all") -> None:
    """Bump version for one or all components."""
    targets = _resolve_components(component)
    print(f"Bumping {bump_type} for: {', '.join(targets)}")
    for comp in targets:
        version = read_ttl_version(comp)
        c = parse_version(version)

        if bump_type == "rc":
            if not c["prerelease"]:
                raise ValueError(
                    f"[{comp}] Cannot bump RC on a non-RC version. Use patch/minor/major first."
                )
            m = re.match(r"rc(\d+)", c["prerelease"])
            if not m:
                raise ValueError(
                    f"[{comp}] Cannot bump non-RC prerelease: {c['prerelease']}"
                )
            c["prerelease"] = f"rc{int(m.group(1)) + 1}"
        elif bump_type == "patch":
            if c["prerelease"]:
                c["prerelease"] = None  # finalise RC → stable patch
            else:
                c["patch"] += 1
        elif bump_type == "minor":
            c["minor"] += 1
            c["patch"] = 0
            c["prerelease"] = None
        elif bump_type == "major":
            c["major"] += 1
            c["minor"] = 0
            c["patch"] = 0
            c["prerelease"] = None
        else:
            raise ValueError(
                f"Invalid bump type: {bump_type!r}. Choose: rc | patch | minor | major"
            )

        write_version(comp, format_version(c))


def set_version(version_str: str, component: str = "all") -> None:
    """Set an explicit version for one or all components."""
    parse_version(version_str)  # validate format
    targets = _resolve_components(component)
    print(f"Setting {version_str} for: {', '.join(targets)}")
    for comp in targets:
        write_version(comp, version_str)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]

    try:
        if cmd == "get":
            component = args[1] if len(args) > 1 else "mas"
            if component == "all":
                for c in COMPONENTS:
                    print(f"{c}={read_ttl_version(c)}")
            else:
                # Graceful: unknown component defaults to mas (backward compat)
                print(read_ttl_version(component if component in COMPONENTS else "mas"))

        elif cmd == "get-full":
            component = args[1] if len(args) > 1 else "mas"
            print(
                get_version_with_metadata(
                    component if component in COMPONENTS else "mas"
                )
            )

        elif cmd == "bump":
            if len(args) < 2:
                print(
                    "Error: bump requires type (rc, patch, minor, major)",
                    file=sys.stderr,
                )
                sys.exit(1)
            bump_type = args[1]
            component = args[2] if len(args) > 2 else "all"
            bump_version(bump_type, component)

        elif cmd == "set":
            if len(args) < 2:
                print("Error: set requires version string", file=sys.stderr)
                sys.exit(1)
            version = args[1]
            component = args[2] if len(args) > 2 else "all"
            set_version(version, component)

        else:
            print(f"Error: Unknown command {cmd!r}", file=sys.stderr)
            print(__doc__)
            sys.exit(1)

    except (ValueError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
