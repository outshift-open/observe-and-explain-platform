#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""The session's trace as a temporary file the agent reads through tools.

The worker fetches the whole trajectory first (it is the only part that talks to the API and the
graph) and writes it here, one JSON line per step. The agent never gets a client, only the three
read-only questions ``TraceFile`` answers: list the steps, read a window of one step, grep. Only
one step is held in memory at a time. The directory is removed when the ``with`` block ends, whether
the detection succeeded, failed or was cancelled; ``sweep_stale`` removes what a killed process left.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DIR_PREFIX = "cognitive-failure-trace-"
STALE_AFTER_SECONDS = 3600

# One text field is cut to this many characters when written, so one huge step cannot fill the disk.
MAX_FIELD_CHARS = 200_000
PREVIEW_CHARS = 80
MAX_PATTERN_CHARS = 200
FIELDS = ("input", "output")


def _clip(text: str | None) -> str:
    text = (text or "").strip()
    if len(text) <= MAX_FIELD_CHARS:
        return text
    head, tail = int(MAX_FIELD_CHARS * 0.6), int(MAX_FIELD_CHARS * 0.4)
    return f"{text[:head]} …[{len(text) - head - tail} characters cut]… {text[-tail:]}"


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW_CHARS else flat[:PREVIEW_CHARS] + "…"


def sweep_stale(directory: str | None = None, max_age: float = STALE_AFTER_SECONDS) -> int:
    """Remove trace directories older than ``max_age`` seconds (left by a process that died). Returns how many."""
    root = Path(directory or tempfile.gettempdir())
    removed = 0
    try:
        candidates = list(root.glob(f"{DIR_PREFIX}*"))
    except OSError:
        return 0
    for path in candidates:
        try:
            if path.is_dir() and time.time() - path.stat().st_mtime > max_age:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("Removed %d stale trace director%s", removed, "y" if removed == 1 else "ies")
    return removed


class TraceFile:
    """A trajectory written to a private temporary file, deleted on exit."""

    def __init__(self, trajectory: Mapping[str, Any], directory: str | None = None):
        self._trajectory = trajectory
        self._parent = directory
        self._dir: Path | None = None
        self._path: Path | None = None
        # Per step: (call_id, offset, length in the file, summary). Small; the text stays on disk.
        self._index: list[tuple[str, int, int, dict[str, Any]]] = []
        self._by_id: dict[str, int] = {}

    # ------------------------------------------------------------ lifecycle

    def __enter__(self) -> "TraceFile":
        self._dir = Path(tempfile.mkdtemp(prefix=DIR_PREFIX, dir=self._parent))  # mode 0700
        self._path = self._dir / "steps.jsonl"
        try:
            self._write()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        if self._dir is not None:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None
            self._path = None

    @property
    def path(self) -> Path | None:
        return self._path

    def _write(self) -> None:
        assert self._path is not None
        with self._path.open("wb") as handle:
            for position, step in enumerate(self._trajectory.get("steps") or []):
                call_id = str(step["call_id"])
                record = {
                    "call_id": call_id,
                    "kind": step.get("kind"),
                    "name": step.get("name"),
                    "agent_id": step.get("agent_id"),
                    "success": step.get("success"),
                    "input": _clip(step.get("input_text")),
                    "output": _clip(step.get("output_text")),
                }
                line = json.dumps(record, ensure_ascii=False).encode("utf-8") + b"\n"
                offset = handle.tell()
                handle.write(line)
                summary = {
                    "position": position,
                    "call_id": call_id,
                    "kind": record["kind"],
                    "name": record["name"],
                    "agent_id": record["agent_id"],
                    "success": record["success"],
                    "input_chars": len(record["input"]),
                    "output_chars": len(record["output"]),
                    "preview": _preview(record["input"]),
                }
                self._by_id.setdefault(call_id, len(self._index))
                self._index.append((call_id, offset, len(line), summary))

    # ------------------------------------------------------------ what the agent can ask

    @property
    def step_ids(self) -> set[str]:
        return set(self._by_id)

    def __len__(self) -> int:
        return len(self._index)

    @staticmethod
    def _label(summary: Mapping[str, Any]) -> str:
        label = f"#{summary['position']} {summary['call_id']} | {summary['kind']} {summary['name']}"
        if summary["agent_id"]:
            label += f" (agent: {summary['agent_id']})"
        if summary["success"] is False:
            label += " [FAILED]"
        return f"{label} | in {summary['input_chars']} chars, out {summary['output_chars']} chars"

    def list_steps(self, offset: int = 0, limit: int = 50) -> str:
        """One line per step: position, id, kind, name, agent, sizes and the start of its input."""
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 200))
        rows = self._index[offset : offset + limit]
        if not rows:
            return f"No step at offset {offset}: the trace has {len(self)} steps."
        lines = [f"{self._label(s)} | {s['preview']!r}" for *_, s in rows]
        end = offset + len(rows)
        if end < len(self):
            lines.append(f"[steps {offset}-{end - 1} of {len(self)}; next offset {end}]")
        return "\n".join(lines)

    def _read_record(self, position: int) -> dict[str, Any]:
        assert self._path is not None
        _, offset, length, _ = self._index[position]
        with self._path.open("rb") as handle:
            handle.seek(offset)
            return json.loads(handle.read(length))

    def read_step(self, call_id: str, field: str = "both", offset: int = 0, length: int = 4000) -> str:
        """A window of a step's input and/or output text, with where to continue."""
        position = self._by_id.get(str(call_id).strip())
        if position is None:
            return f"Unknown step {call_id!r}. Use list_steps or grep to find step ids."
        if field not in (*FIELDS, "both"):
            return f"field must be 'input', 'output' or 'both', not {field!r}."
        offset, length = max(0, int(offset)), max(1, min(int(length), 8000))
        record = self._read_record(position)
        parts = [self._label(self._index[position][3])]
        for name in FIELDS if field == "both" else (field,):
            text = record[name]
            window = text[offset : offset + length]
            end = offset + len(window)
            note = f"chars {offset}-{end} of {len(text)}" + (f"; continue at offset {end}" if end < len(text) else "")
            parts.append(f"{name.upper()} [{note}]:\n{window}")
        return "\n".join(parts)

    def grep(self, pattern: str, field: str = "both", max_matches: int = 20, context: int = 100) -> str:
        """Regex search (case-insensitive) over the steps' texts; each match with a little context."""
        if len(pattern) > MAX_PATTERN_CHARS:
            return f"Pattern too long (max {MAX_PATTERN_CHARS} characters)."
        if field not in (*FIELDS, "both"):
            return f"field must be 'input', 'output' or 'both', not {field!r}."
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as exc:
            return f"Invalid regular expression: {exc}"
        max_matches, context = max(1, min(int(max_matches), 50)), max(0, min(int(context), 400))
        assert self._path is not None
        found: list[str] = []
        more = False
        with self._path.open("rb") as handle:
            for raw in handle:
                record = json.loads(raw)
                for name in FIELDS if field == "both" else (field,):
                    text = record[name]
                    for match in regex.finditer(text):
                        if len(found) >= max_matches:
                            more = True
                            break
                        start, end = max(0, match.start() - context), min(len(text), match.end() + context)
                        snippet = " ".join(text[start:end].split())
                        found.append(f"{record['call_id']} {name} @{match.start()}: …{snippet}…")
                    if more:
                        break
                if more:
                    break
        if not found:
            return f"No match for {pattern!r}."
        if more:
            found.append(f"[more matches than {max_matches}: narrow the pattern]")
        return "\n".join(found)
