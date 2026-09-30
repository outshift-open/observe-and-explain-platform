#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from mce.core.provider import DataProvider
from mce.core.metric import MetricRequirements


class JsonDataProvider(DataProvider):
    """
    Adapter that reads session data from a local JSON file.
    Expects a list of session objects.
    """

    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.data_map: dict[str, dict[str, Any]] = {}
        self._load_data()

    def _load_data(self):
        if not self.file_path.exists():
            raise FileNotFoundError(f"JSON file not found: {self.file_path}")

        with open(self.file_path, "r") as f:
            content = json.load(f)

        if isinstance(content, list):
            for item in content:
                if "id" in item:
                    self.data_map[item["id"]] = item
                elif "session_id" in item:
                    self.data_map[item["session_id"]] = item
        elif isinstance(content, dict):
            # Maybe keyed by ID?
            self.data_map = content
        else:
            raise ValueError(f"Unexpected JSON format in {self.file_path}")

    def fetch(
        self, resource_id: str, requirements: MetricRequirements
    ) -> dict[str, Any]:
        if resource_id not in self.data_map:
            raise LookupError(f"Session {resource_id} not found in {self.file_path}")

        data = self.data_map[resource_id].copy()

        # Preprocessing: Bucketize spans for Engine convenience
        if "spans" in data and isinstance(data["spans"], list):
            data["tool_spans"] = [s for s in data["spans"] if s.get("type") == "tool"]
            data["llm_spans"] = [s for s in data["spans"] if s.get("type") == "llm"]

        # Ensure a "session" dict exists so session metrics (e.g. Duration)
        # can read timing via _detect_resource_type → context["session"].
        # Use the top-level data as the session node; it may already carry
        # startTime / duration if the JSON file stores them there.
        if "session" not in data:
            data["session"] = {
                k: v
                for k, v in data.items()
                if k not in ("spans", "tool_spans", "llm_spans", "agent_spans")
            }

        return data

    def list_session_ids(self) -> list[str]:
        return list(self.data_map.keys())
