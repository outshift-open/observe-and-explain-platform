#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""TAU-2 Trajectory to ClickHouse Importer.

Transforms TAU-2 trajectory JSON files into the ClickHouse `otel_traces` schema
so they can be queried via the API layer like:
    http://localhost:8080/traces/session/tau2-airline_78e610a0-b3f3-4feb-93bd-ea314b83feb8

The MCE data_parser.py reconstructs SpanEntity objects from ClickHouse rows by:
  - SpanName ending in ".chat" → entity_type="llm"
  - SpanName ending in ".tool" → entity_type="tool"
  - SpanAttributes["session.id"] → session grouping
  - SpanAttributes["gen_ai.prompt.*"] → LLM input payloads
  - SpanAttributes["gen_ai.completion.*"] → LLM output payloads
  - SpanAttributes["traceloop.entity.name/input/output"] → tool payloads
  - SpanAttributes["llm.request.functions.*"] → tool definitions
"""

import glob
import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("temporal_evals.importer")

# ============================================================================
# TAU-2 Span → ClickHouse otel_traces row
# ============================================================================


def list_trajectory_json_files(trajectory_dir: str | Path) -> List[str]:
    """List trajectory JSON files, supporting flat and train/test layouts."""
    base_dir = Path(trajectory_dir)

    def _include(path: str) -> bool:
        name = Path(path).name
        if name.startswith("import_manifest_"):
            return False
        # TAU2 directories include helper files like _index.json.
        if name.startswith("_"):
            return False
        return True

    top_level = [
        file_path
        for file_path in sorted(glob.glob(str(base_dir / "*.json")))
        if _include(file_path)
    ]
    if top_level:
        return top_level

    nested: List[str] = []
    for subdir_name in ("train", "test"):
        nested.extend(
            file_path
            for file_path in sorted(glob.glob(str(base_dir / subdir_name / "*.json")))
            if _include(file_path)
        )
    return nested


def _build_session_id(domain: str, trace_id: str) -> str:
    """Build session ID in the format the API layer expects.

    The session handler splits on '_' to extract the UUID:
        splitByChar('_', SpanAttributes['session.id'])[2]
    So we use: tau2-{domain}_{trace_id}
    """
    return f"tau2-{domain}_{trace_id}"


def _build_span_name(entity_type: str, entity_name: str) -> str:
    """Build SpanName that MCE's data_parser recognises.

    data_parser uses SpanName suffix to determine entity_type:
        .chat → llm
        .tool → tool
        .agent → agent
        .workflow → workflow
    """
    suffix_map = {
        "llm": "chat",
        "tool": "tool",
        "agent": "agent",
        "workflow": "workflow",
    }
    suffix = suffix_map.get(entity_type, entity_type)
    return f"{entity_name}.{suffix}"


def _stringify_attr_value(value: Any) -> str:
    """Serialize values for Map(String, String) span attributes."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, default=str)
    return str(value)


def _normalize_model_name_for_request(model_name: str) -> str:
    """Convert versioned model IDs to the request-model format used in NOA traces."""
    if not model_name:
        return "unknown"
    match = re.match(r"^(.+)-\d{4}-\d{2}-\d{2}$", model_name)
    return match.group(1) if match else model_name


def _normalize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    """Normalize tool calls to a list of dict entries."""
    if tool_calls is None:
        return []
    if isinstance(tool_calls, str):
        try:
            tool_calls = json.loads(tool_calls)
        except Exception:
            return []
    if isinstance(tool_calls, dict):
        tool_calls = [tool_calls]
    if not isinstance(tool_calls, list):
        return []
    return [call for call in tool_calls if isinstance(call, dict)]


def _stringify_tool_arguments(arguments: Any) -> str:
    """Store tool-call arguments in a stable JSON-string form."""
    if arguments is None:
        return "{}"
    if isinstance(arguments, str):
        raw = arguments.strip()
        if not raw:
            return "{}"
        if raw.startswith("{") or raw.startswith("["):
            return arguments
        return json.dumps({"value": arguments}, default=str)
    return json.dumps(arguments, default=str)


def _flatten_tool_calls(
    attrs: Dict[str, str],
    prefix: str,
    tool_calls: Any,
) -> List[str]:
    """Emit flattened tool-call fields expected by MCE."""
    normalized_calls = _normalize_tool_calls(tool_calls)
    tool_names: List[str] = []
    for tool_idx, tool_call in enumerate(normalized_calls):
        function_info = tool_call.get("function")
        tool_name = tool_call.get("name")
        tool_id = tool_call.get("id") or tool_call.get("tool_call_id")
        arguments = tool_call.get("arguments")

        if isinstance(function_info, dict):
            if not tool_name:
                tool_name = function_info.get("name")
            if arguments is None:
                arguments = function_info.get("arguments")

        if tool_name:
            attrs[f"{prefix}.tool_calls.{tool_idx}.name"] = _stringify_attr_value(
                tool_name
            )
            tool_names.append(str(tool_name))
        if tool_id:
            attrs[f"{prefix}.tool_calls.{tool_idx}.id"] = _stringify_attr_value(tool_id)
        attrs[f"{prefix}.tool_calls.{tool_idx}.arguments"] = _stringify_tool_arguments(
            arguments
        )
    return tool_names


def _normalize_tool_definitions(tool_definition: Any) -> List[Dict[str, Any]]:
    """Normalize tool definitions to a list for llm.request.functions.* mapping."""
    if tool_definition is None:
        return []
    if isinstance(tool_definition, str):
        try:
            tool_definition = json.loads(tool_definition)
        except Exception:
            return []
    if isinstance(tool_definition, dict):
        return [tool_definition]
    if isinstance(tool_definition, list):
        return [item for item in tool_definition if isinstance(item, dict)]
    return []


def _llm_span_to_span_attributes(
    span: Dict[str, Any],
    session_id: str,
) -> Dict[str, str]:
    """Convert a TAU-2 LLM span into ClickHouse SpanAttributes map.

    MCE's data_parser expects:
      gen_ai.prompt.{i}.role / gen_ai.prompt.{i}.content  → input
      gen_ai.completion.{i}.role / gen_ai.completion.{i}.content → output
      gen_ai.response.model → entity_name
      gen_ai.request.model → model name
      llm.request.functions.{i}.* → tool definitions (if tool_calls present)
    """
    attrs: Dict[str, str] = {
        "session.id": session_id,
        "traceloop.span.kind": "llm",
    }

    entity_name = _stringify_attr_value(span.get("entity_name", "unknown"))
    attrs["gen_ai.response.model"] = entity_name
    attrs["gen_ai.request.model"] = _normalize_model_name_for_request(entity_name)
    attrs["llm.request.type"] = "chat"

    # --- Input: messages → gen_ai.prompt.{i}.* ---
    input_payload = span.get("input_payload") or {}
    messages = input_payload.get("messages", [])
    tool_names_in_span: List[str] = []
    for i, msg in enumerate(messages):
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            attrs[f"gen_ai.prompt.{i}.role"] = _stringify_attr_value(role)
            attrs[f"gen_ai.prompt.{i}.content"] = _stringify_attr_value(content)
            if role == "system" and "gen_ai.system" not in attrs:
                attrs["gen_ai.system"] = _stringify_attr_value(content)
            tool_names_in_span.extend(
                _flatten_tool_calls(attrs, f"gen_ai.prompt.{i}", msg.get("tool_calls"))
            )
        elif isinstance(msg, str):
            attrs[f"gen_ai.prompt.{i}.role"] = "user"
            attrs[f"gen_ai.prompt.{i}.content"] = msg

    # If no messages but user_message exists
    if not messages and input_payload.get("user_message"):
        attrs["gen_ai.prompt.0.role"] = "user"
        attrs["gen_ai.prompt.0.content"] = _stringify_attr_value(
            input_payload["user_message"]
        )

    # --- Output: response → gen_ai.completion.0.* ---
    output_payload = span.get("output_payload") or {}
    content = output_payload.get("content", "")
    completion_role = output_payload.get("role", "assistant")
    attrs["gen_ai.completion.0.role"] = _stringify_attr_value(completion_role)
    attrs["gen_ai.completion.0.content"] = _stringify_attr_value(content)

    # Tool calls in output
    tool_names_in_span.extend(
        _flatten_tool_calls(
            attrs, "gen_ai.completion.0", output_payload.get("tool_calls")
        )
    )

    finish_reason = output_payload.get("finish_reason")
    if finish_reason is None:
        finish_reason = (span.get("attrs") or {}).get("finish_reason")
    if finish_reason is not None:
        attrs["gen_ai.completion.0.finish_reason"] = _stringify_attr_value(
            finish_reason
        )

    # --- Usage tokens ---
    usage = output_payload.get("usage", {})
    if isinstance(usage, dict):
        if "prompt_tokens" in usage:
            attrs["gen_ai.usage.prompt_tokens"] = str(usage["prompt_tokens"])
        if "completion_tokens" in usage:
            attrs["gen_ai.usage.completion_tokens"] = str(usage["completion_tokens"])
        total = usage.get("total_tokens")
        if total is None and "prompt_tokens" in usage and "completion_tokens" in usage:
            total = usage["prompt_tokens"] + usage["completion_tokens"]
        if total is not None:
            attrs["llm.usage.total_tokens"] = str(total)

    # --- Tool definitions (from the LLM's available functions) ---
    normalized_defs = _normalize_tool_definitions(span.get("tool_definition"))
    if normalized_defs:
        for i, tool_def in enumerate(normalized_defs):
            name = tool_def.get("name") or tool_def.get("function", {}).get("name", "")
            if not name:
                continue
            attrs[f"llm.request.functions.{i}.name"] = _stringify_attr_value(name)
            description = tool_def.get(
                "description", tool_def.get("function", {}).get("description")
            )
            if description is not None:
                attrs[f"llm.request.functions.{i}.description"] = _stringify_attr_value(
                    description
                )
            params = tool_def.get("parameters") or tool_def.get("function", {}).get(
                "parameters"
            )
            if params is not None:
                attrs[f"llm.request.functions.{i}.parameters"] = json.dumps(
                    params, default=str
                )
    else:
        # TAU2 traces usually do not include explicit function specs.
        for i, tool_name in enumerate(sorted(set(tool_names_in_span))):
            attrs[f"llm.request.functions.{i}.name"] = _stringify_attr_value(tool_name)

    return attrs


def _tool_span_to_span_attributes(
    span: Dict[str, Any],
    session_id: str,
) -> Dict[str, str]:
    """Convert a TAU-2 tool span into ClickHouse SpanAttributes map.

    MCE's data_parser expects:
      traceloop.entity.name → tool name
      traceloop.entity.input → JSON string of input payload
      traceloop.entity.output → JSON string of output payload
    """
    entity_name = _stringify_attr_value(span.get("entity_name", "unknown"))

    attrs: Dict[str, str] = {
        "session.id": session_id,
        "traceloop.span.kind": "tool",
        "traceloop.entity.name": entity_name,
    }

    input_payload = span.get("input_payload")
    if input_payload is not None:
        attrs["traceloop.entity.input"] = json.dumps(input_payload, default=str)

    output_payload = span.get("output_payload")
    if output_payload is not None:
        attrs["traceloop.entity.output"] = json.dumps(output_payload, default=str)

    # Store tool definition so it can be reconstructed
    tool_def = span.get("tool_definition")
    if tool_def:
        attrs["tool_definition"] = json.dumps(tool_def, default=str)

    return attrs


def tau2_span_to_otel_row(
    span: Dict[str, Any],
    trajectory: Dict[str, Any],
    domain: str,
    span_index: int,
) -> Dict[str, Any]:
    """Convert a single TAU-2 span to a ClickHouse otel_traces row.

    Args:
        span: A span dict from the trajectory's "spans" array
        trajectory: The top-level trajectory dict (for trace_id, timestamps, etc.)
        domain: Domain name (airline, retail, etc.)
        span_index: Index of this span within the trajectory

    Returns:
        Dict matching the otel_traces ClickHouse schema
    """
    trace_id = trajectory.get("id") or span.get("trace_id") or str(uuid.uuid4())
    session_id = _build_session_id(domain, trace_id)

    entity_type = span.get("entity_type", "other")
    entity_name = span.get("entity_name", "unknown")
    app_name = span.get("app_name", f"tau2-bench-{domain}")

    # Parse timestamp
    timestamp_str = (
        span.get("timestamp")
        or trajectory.get("timestamp")
        or datetime.utcnow().isoformat()
    )
    try:
        timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        timestamp = datetime.utcnow()

    # Build SpanAttributes based on entity type
    if entity_type == "llm":
        span_attributes = _llm_span_to_span_attributes(span, session_id)
    elif entity_type == "tool":
        span_attributes = _tool_span_to_span_attributes(span, session_id)
    else:
        # Generic fallback
        span_attributes = {
            "session.id": session_id,
            "traceloop.span.kind": entity_type.lower(),
            "traceloop.entity.name": _stringify_attr_value(entity_name),
        }
        if span.get("input_payload"):
            span_attributes["traceloop.entity.input"] = json.dumps(
                span["input_payload"], default=str
            )
        if span.get("output_payload"):
            span_attributes["traceloop.entity.output"] = json.dumps(
                span["output_payload"], default=str
            )

    # Build the ClickHouse row
    span_id = span.get("span_id") or str(uuid.uuid4())
    parent_span_id = span.get("parent_span_id") or ""

    # Status
    contains_error = bool(span.get("contains_error", False))
    if not contains_error and entity_type == "tool":
        contains_error = bool((span.get("output_payload") or {}).get("error"))
    status_code = "STATUS_CODE_ERROR" if contains_error else "STATUS_CODE_OK"

    # Duration (nanoseconds) — TAU-2 may not have this
    duration_ns = 0
    if span.get("duration"):
        try:
            duration_ns = int(float(span["duration"]) * 1e6)  # ms → ns
        except (ValueError, TypeError):
            pass

    # Events (for errors)
    events_timestamps: List[str] = []
    events_names: List[str] = []
    events_attributes: List[Dict[str, str]] = []

    return {
        "Timestamp": timestamp,
        "TraceId": trace_id,
        "SpanId": span_id,
        "ParentSpanId": parent_span_id,
        "TraceState": "",
        "SpanName": _build_span_name(entity_type, entity_name),
        "SpanKind": "SPAN_KIND_INTERNAL",
        "ServiceName": app_name,
        "ResourceAttributes": {"service.name": app_name},
        "ScopeName": "tau2-bench",
        "ScopeVersion": "1.0.0",
        "SpanAttributes": span_attributes,
        "Duration": duration_ns,
        "StatusCode": status_code,
        "StatusMessage": "",
        "Events.Timestamp": events_timestamps,
        "Events.Name": events_names,
        "Events.Attributes": events_attributes,
        "Links.TraceId": [],
        "Links.SpanId": [],
        "Links.TraceState": [],
        "Links.Attributes": [],
    }


# ============================================================================
# Full trajectory → list of rows
# ============================================================================


def trajectory_to_otel_rows(
    trajectory_path: str,
    domain: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Convert an entire TAU-2 trajectory file to ClickHouse otel_traces rows.

    Args:
        trajectory_path: Path to the trajectory JSON file
        domain: Domain name (airline, retail, telecom, noa)

    Returns:
        Tuple of (list of otel_traces rows, trajectory metadata)
    """
    with open(trajectory_path, "r") as f:
        trajectory = json.load(f)

    rows = []
    for i, span in enumerate(trajectory.get("spans", [])):
        row = tau2_span_to_otel_row(span, trajectory, domain, i)
        rows.append(row)

    metadata = {
        "trajectory_id": trajectory.get("id"),
        "task_id": trajectory.get("task_id"),
        "reward": trajectory.get("reward_info", {}).get("reward"),
        "num_spans": len(rows),
        "session_id": _build_session_id(domain, trajectory.get("id", "unknown")),
        "source_file": str(trajectory_path),
    }
    if metadata["reward"] is None:
        metadata["reward"] = trajectory.get("reward")

    return rows, metadata


# ============================================================================
# Batch import: directory of trajectories → ClickHouse
# ============================================================================


_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_table_name(table_name: str) -> None:
    """Allow only simple identifier table names in generated SQL."""
    if not _TABLE_NAME_RE.match(table_name):
        raise ValueError(
            f"Invalid table name '{table_name}'. "
            "Use letters, numbers, and underscores only."
        )


def _ensure_otel_traces_table(client: Any, table_name: str) -> None:
    """Create the otel_traces-like table if missing."""
    _validate_table_name(table_name)
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name}
        (
            `Timestamp` DateTime64(9),
            `TraceId` String,
            `SpanId` String,
            `ParentSpanId` String,
            `TraceState` String,
            `SpanName` LowCardinality(String),
            `SpanKind` LowCardinality(String),
            `ServiceName` LowCardinality(String),
            `ResourceAttributes` Map(String, String),
            `ScopeName` String,
            `ScopeVersion` String,
            `SpanAttributes` Map(String, String),
            `Duration` UInt64,
            `StatusCode` LowCardinality(String),
            `StatusMessage` String,
            `Events.Timestamp` Array(DateTime64(9)) DEFAULT [],
            `Events.Name` Array(LowCardinality(String)) DEFAULT [],
            `Events.Attributes` Array(Map(String, String)) DEFAULT [],
            `Links.TraceId` Array(String) DEFAULT [],
            `Links.SpanId` Array(String) DEFAULT [],
            `Links.TraceState` Array(String) DEFAULT [],
            `Links.Attributes` Array(Map(String, String)) DEFAULT []
        )
        ENGINE = MergeTree
        ORDER BY (TraceId, Timestamp, SpanId)
        """
    )


def _domain_cleanup_where_clause(domain: str) -> str:
    """Build a ClickHouse WHERE clause that targets rows for a given domain."""
    if domain == "noa":
        return (
            "("
            "SpanAttributes['session.id'] LIKE 'tau2-noa_%' "
            "OR SpanAttributes['session.id'] LIKE 'noa-trip-planner_%' "
            "OR SpanAttributes['session.id'] LIKE 'noa-trip-planner-mas_%' "
            "OR ServiceName LIKE 'noa-trip-planner%'"
            ")"
        )

    return (
        "("
        f"SpanAttributes['session.id'] LIKE 'tau2-{domain}_%' "
        f"OR ServiceName = 'tau2-bench-{domain}'"
        ")"
    )


def _clear_domain_rows(
    client: Any,
    table_name: str,
    domain: str,
) -> Dict[str, Any]:
    """Delete existing rows for a domain so imports are clean and deterministic."""
    _validate_table_name(table_name)
    where_clause = _domain_cleanup_where_clause(domain)

    count_before_query = f"SELECT count() FROM {table_name} WHERE {where_clause}"
    before_result = client.query(count_before_query)
    rows_before = (
        int(before_result.result_rows[0][0]) if before_result.result_rows else 0
    )

    if rows_before == 0:
        return {"rows_before": 0, "rows_deleted": 0, "rows_after": 0}

    client.command(
        f"ALTER TABLE {table_name} DELETE WHERE {where_clause} "
        "SETTINGS mutations_sync = 1"
    )

    count_after_query = f"SELECT count() FROM {table_name} WHERE {where_clause}"
    after_result = client.query(count_after_query)
    rows_after = int(after_result.result_rows[0][0]) if after_result.result_rows else 0
    rows_deleted = max(rows_before - rows_after, 0)

    return {
        "rows_before": rows_before,
        "rows_deleted": rows_deleted,
        "rows_after": rows_after,
    }


def import_trajectories_to_clickhouse(
    trajectory_dir: str,
    domain: str,
    clickhouse_url: str = "localhost",
    clickhouse_port: int = 8123,
    clickhouse_user: str = "admin",
    clickhouse_password: str = "admin",
    clickhouse_db: str = "default",
    table_name: str = "otel_traces",
    max_files: Optional[int] = None,
    clear_existing_domain: bool = True,
) -> Dict[str, Any]:
    """Import TAU-2 trajectories from a directory into ClickHouse.

    Args:
        trajectory_dir: Path to directory containing trajectory JSON files
        domain: Domain name (airline, retail, etc.)
        clickhouse_url: ClickHouse host
        clickhouse_port: ClickHouse HTTP port (8123)
        clickhouse_user: ClickHouse username
        clickhouse_password: ClickHouse password
        clickhouse_db: ClickHouse database name
        table_name: Target table (default: otel_traces)
        max_files: Max files to import (None = all)
        clear_existing_domain: Delete existing rows for this domain before import

    Returns:
        Summary dict with counts and session IDs
    """
    try:
        import clickhouse_connect
    except ImportError:
        raise ImportError(
            "clickhouse-connect is required for ClickHouse import. "
            "Install with: pip install clickhouse-connect"
        )

    # Connect to ClickHouse
    client = clickhouse_connect.get_client(
        host=clickhouse_url,
        port=clickhouse_port,
        username=clickhouse_user,
        password=clickhouse_password,
        database=clickhouse_db,
    )

    logger.info(
        f"Connected to ClickHouse at {clickhouse_url}:{clickhouse_port}/{clickhouse_db}"
    )
    _ensure_otel_traces_table(client, table_name)
    logger.info(f"Ensured table exists: {clickhouse_db}.{table_name}")
    cleared_stats = {
        "rows_before": 0,
        "rows_deleted": 0,
        "rows_after": 0,
    }
    if clear_existing_domain:
        cleared_stats = _clear_domain_rows(client, table_name, domain)
        logger.info(
            "Cleared existing '%s' rows: before=%s, deleted=%s, after=%s",
            domain,
            cleared_stats["rows_before"],
            cleared_stats["rows_deleted"],
            cleared_stats["rows_after"],
        )

    # Collect all trajectory files (supports flat and train/test layouts).
    files = list_trajectory_json_files(trajectory_dir)
    if max_files:
        files = files[:max_files]

    logger.info(f"Found {len(files)} trajectory files in {trajectory_dir}")

    all_rows = []
    all_metadata = []
    session_ids = []
    # Manifest: session_id → source file + metadata
    manifest: Dict[str, Any] = {}

    for file_path in files:
        try:
            rows, metadata = trajectory_to_otel_rows(file_path, domain)
            all_rows.extend(rows)
            all_metadata.append(metadata)
            session_ids.append(metadata["session_id"])

            # Build manifest entry
            manifest[metadata["session_id"]] = {
                "source_file": str(file_path),
                "filename": Path(file_path).name,
                "trajectory_id": metadata["trajectory_id"],
                "task_id": metadata["task_id"],
                "reward": metadata["reward"],
                "num_spans": metadata["num_spans"],
            }

            logger.info(
                f"  {Path(file_path).name}: {metadata['num_spans']} spans → "
                f"session={metadata['session_id']}"
            )
        except Exception as e:
            logger.error(f"  Error processing {file_path}: {e}")

    if not all_rows:
        return {
            "status": "no_data",
            "files_processed": 0,
            "cleared_existing": cleared_stats,
        }

    # Insert into ClickHouse
    # Build column lists matching the otel_traces schema
    columns = [
        "Timestamp",
        "TraceId",
        "SpanId",
        "ParentSpanId",
        "TraceState",
        "SpanName",
        "SpanKind",
        "ServiceName",
        "ResourceAttributes",
        "ScopeName",
        "ScopeVersion",
        "SpanAttributes",
        "Duration",
        "StatusCode",
        "StatusMessage",
    ]

    data = []
    for row in all_rows:
        data.append(
            [
                row["Timestamp"],
                row["TraceId"],
                row["SpanId"],
                row["ParentSpanId"],
                row["TraceState"],
                row["SpanName"],
                row["SpanKind"],
                row["ServiceName"],
                row["ResourceAttributes"],
                row["ScopeName"],
                row["ScopeVersion"],
                row["SpanAttributes"],
                row["Duration"],
                row["StatusCode"],
                row["StatusMessage"],
            ]
        )

    logger.info(f"Inserting {len(data)} rows into {clickhouse_db}.{table_name}...")

    client.insert(
        table=table_name,
        data=data,
        column_names=columns,
    )

    logger.info(f"Successfully inserted {len(data)} rows")

    # Save manifest JSON: session_id → source file mapping
    manifest_path = Path(trajectory_dir) / f"import_manifest_{domain}.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    logger.info(f"Manifest saved to {manifest_path}")

    return {
        "status": "success",
        "files_processed": len(files),
        "total_spans_inserted": len(data),
        "session_ids": session_ids,
        "cleared_existing": cleared_stats,
        "domain": domain,
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "trajectories": all_metadata,
    }
