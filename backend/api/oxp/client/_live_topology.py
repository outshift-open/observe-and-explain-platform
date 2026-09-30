#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Live topology methods for :class:`LocalClient`."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from oxp.connectors.base import Connector
from oxp.core.exceptions import DatabaseError
from oxp.models.live_topology import (
    LiveAgents,
    LiveTopologySessions,
    LiveTools,
    RealtimeTopologyEdge,
    RealtimeTopologyNode,
    RealtimeTopologyResponse,
)
from oxp.query_builders import live_topology as live_topology_queries
from oxp.query_builders.types import Dialect

logger = logging.getLogger(__name__)


class LiveTopologyClient:
    db: Connector
    _dialect: Dialect

    _ORPHAN_SESSION_IDLE_MINUTES = 5
    # Skip re-emitting for the same session within this window even if the
    # newly-written completion event isn't visible in the aggregate query yet.
    _ORPHAN_EMISSION_DEDUPE_SECONDS = 300
    # Bound the amount of write work triggered by a single /sessions request.
    _MAX_ORPHAN_EMISSIONS_PER_CALL = 25

    def _get_orphan_emission_cache(self) -> dict[str, datetime]:
        """Lazily-initialised per-instance dedupe cache: session_id -> emit ts."""
        cache = getattr(self, "_orphan_emission_cache", None)
        if cache is None:
            cache = {}
            self._orphan_emission_cache = cache
        return cache

    @staticmethod
    def _as_utc_datetime(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"

        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    def _emit_synthetic_session_completed_event(
        self, *, session_id: str
    ) -> datetime | None:
        """Insert a synthetic completion event; return its timestamp on success."""
        now = datetime.now(tz=timezone.utc)

        if self._dialect is Dialect.SQLITE:
            payload = {
                "session.id": session_id,
                "synthetic": True,
                "synthetic.reason": "orphan_session_no_recent_activity",
                "synthetic.emitted_at": now.isoformat(),
            }
            command = """
            INSERT INTO otel_logs (
                timestamp,
                span_id,
                body,
                log_attributes,
                service_name,
                duration,
                resource_attributes,
                scope_name,
                event_name,
                application_id,
                agent_id
            ) VALUES (
                :timestamp,
                :span_id,
                :body,
                :log_attributes,
                :service_name,
                :duration,
                :resource_attributes,
                :scope_name,
                :event_name,
                :application_id,
                :agent_id
            )
            """
            params = {
                "timestamp": now.isoformat(),
                "span_id": f"synthetic-{uuid4().hex}",
                "body": "Synthetic topology.session.completed for orphan session",
                "log_attributes": json.dumps(payload),
                "service_name": "oxp.live_topology",
                "duration": 0,
                "resource_attributes": "{}",
                "scope_name": "oxp.live_topology",
                "event_name": "topology.session.completed",
                "application_id": "",
                "agent_id": "",
            }
        else:
            command = """
            INSERT INTO otel_logs (
                Timestamp,
                SpanId,
                Body,
                LogAttributes,
                ServiceName,
                ResourceAttributes,
                ScopeName,
                EventName
            ) VALUES (
                %(timestamp)s,
                %(span_id)s,
                %(body)s,
                map(
                    'session.id', %(session_id)s,
                    'synthetic', 'true',
                    'synthetic.reason', %(synthetic_reason)s,
                    'synthetic.emitted_at', %(synthetic_emitted_at)s
                ),
                %(service_name)s,
                map('service.name', %(service_name)s),
                %(scope_name)s,
                %(event_name)s
            )
            """
            params = {
                "timestamp": now,
                "span_id": f"synthetic-{uuid4().hex}",
                "body": "Synthetic topology.session.completed for orphan session",
                "session_id": session_id,
                "synthetic_reason": "orphan_session_no_recent_activity",
                "synthetic_emitted_at": now.isoformat(),
                "service_name": "oxp.live_topology",
                "scope_name": "oxp.live_topology",
                "event_name": "topology.session.completed",
            }

        try:
            self.db.execute_command(command, params)
            logger.info(
                "Emitted synthetic topology.session.completed for orphan session '%s'",
                session_id,
            )
            return now
        except Exception as exc:
            logger.warning(
                "Failed to emit synthetic session completion for '%s': %s",
                session_id,
                exc,
            )
            return None

    def _reconcile_orphan_sessions(self) -> dict[str, datetime]:
        """Emit synthetic completions for stale orphan sessions.

        Returns a mapping ``session_id -> completion_time`` for sessions
        reconciled during this call. The caller uses this to patch the
        in-memory sessions listing without an extra query round-trip.
        """
        stmt = live_topology_queries.get_orphan_live_topology_sessions(self._dialect)
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            logger.warning("Failed orphan-session reconciliation lookup: %s", exc)
            return {}

        now = datetime.now(tz=timezone.utc)
        idle_cutoff = now - timedelta(minutes=self._ORPHAN_SESSION_IDLE_MINUTES)
        dedupe_cutoff = now - timedelta(seconds=self._ORPHAN_EMISSION_DEDUPE_SECONDS)
        cache = self._get_orphan_emission_cache()
        # Purge stale dedupe entries so the cache doesn't grow unbounded.
        for stale_id in [sid for sid, ts in cache.items() if ts < dedupe_cutoff]:
            cache.pop(stale_id, None)

        reconciled: dict[str, datetime] = {}

        for row in rows:
            if len(reconciled) >= self._MAX_ORPHAN_EMISSIONS_PER_CALL:
                logger.info(
                    "Orphan reconciliation cap (%d) reached; deferring remaining"
                    " orphans to the next call",
                    self._MAX_ORPHAN_EMISSIONS_PER_CALL,
                )
                break

            session_id = str(row[0]) if row and row[0] else ""
            if not session_id:
                continue
            if session_id in cache:
                # Already emitted recently; skip until dedupe window elapses.
                continue

            last_activity = self._as_utc_datetime(row[1] if len(row) > 1 else None)
            if last_activity is None:
                continue
            if last_activity > idle_cutoff:
                continue

            emitted_at = self._emit_synthetic_session_completed_event(
                session_id=session_id
            )
            if emitted_at is not None:
                reconciled[session_id] = emitted_at
                cache[session_id] = emitted_at

        return reconciled

    # ── GET /sessions ─────────────────────────────────────────────────────

    def get_live_topology_sessions(
        self, *, application_name: str | None = None
    ) -> LiveTopologySessions:
        """Return live topology sessions."""
        reconciled = self._reconcile_orphan_sessions()
        stmt = live_topology_queries.get_live_topology_sessions(
            self._dialect, application_name=application_name
        )
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            raise DatabaseError(f"Failed to get live topology sessions: {exc}") from exc

        sessions: list[dict[str, object]] = []
        for row in rows:
            session_id = str(row[0]) if row[0] is not None else ""
            has_completed = bool(row[2])
            end_time_val = row[3]

            if not has_completed and session_id in reconciled:
                has_completed = True
                if not end_time_val:
                    end_time_val = reconciled[session_id].isoformat()

            sessions.append(
                {
                    "session_id": row[0],
                    "start_time": str(row[1]),
                    "status": "completed" if has_completed else "active",
                    "end_time": str(end_time_val) if end_time_val else None,
                }
            )

        return LiveTopologySessions(sessions=sessions)

    # ── GET /agents ───────────────────────────────────────────────────────

    def get_live_agents(self) -> LiveAgents:
        """Return live topology agents."""
        stmt = live_topology_queries.get_live_topology_agents(self._dialect)
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            raise DatabaseError(f"Failed to get live topology agents: {exc}") from exc

        def _to_int(value: object) -> int:
            try:
                return int(value) if value is not None else 0
            except (TypeError, ValueError):
                return 0

        return LiveAgents(
            agents=[
                {
                    "agent_name": row[0],
                    "start_time": str(row[1]),
                    "status": (
                        "active" if _to_int(row[2]) > _to_int(row[3]) else "completed"
                    ),
                    "end_time": (
                        str(row[4])
                        if row[4] and _to_int(row[2]) <= _to_int(row[3])
                        else None
                    ),
                }
                for row in rows
            ]
        )

    # ── GET /tools ────────────────────────────────────────────────────────

    def get_live_tools(self) -> LiveTools:
        """Return live topology tools."""
        stmt = live_topology_queries.get_live_topology_tools(self._dialect)
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            raise DatabaseError(f"Failed to get live topology tools: {exc}") from exc

        def _to_int(value: object) -> int:
            try:
                return int(value) if value is not None else 0
            except (TypeError, ValueError):
                return 0

        def _infer_tools_from_agent_input(
            *, current_agent: str, payload: object
        ) -> dict[str, dict[str, object]]:
            """Infer tool details from an agent input payload."""
            if not isinstance(payload, dict):
                return {}

            args = payload.get("args")
            if not isinstance(args, list) or not args:
                return {}

            first_arg = args[0]
            if not isinstance(first_arg, dict):
                return {}

            messages = first_arg.get("messages")
            if not isinstance(messages, list) or not messages:
                return {}

            decision_index: int | None = None
            for idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue
                if str(msg.get("type") or "") != "AIMessage":
                    continue
                content = msg.get("content")
                if not isinstance(content, str):
                    continue
                first_line = content.splitlines()[0].strip() if content else ""
                if not first_line.startswith("DECISION:"):
                    continue
                decided_agent = first_line.split("DECISION:", 1)[1].strip()
                if decided_agent == current_agent:
                    decision_index = idx

            if decision_index is None:
                return {}

            inferred: dict[str, dict[str, object]] = {}
            for msg in messages[decision_index + 1 :]:
                if not isinstance(msg, dict):
                    continue

                msg_type = str(msg.get("type") or "")
                if msg_type == "AIMessage":
                    content = msg.get("content")
                    if isinstance(content, str):
                        first_line = content.splitlines()[0].strip() if content else ""
                        if first_line.startswith("DECISION:"):
                            break

                    tool_calls = msg.get("tool_calls")
                    if isinstance(tool_calls, list):
                        for call in tool_calls:
                            if not isinstance(call, dict):
                                continue
                            name = str(call.get("name") or "")
                            if not name:
                                continue
                            inferred.setdefault(
                                name,
                                {
                                    "status": "active",
                                },
                            )
                elif msg_type == "ToolMessage":
                    name = str(msg.get("name") or "")
                    if name:
                        inferred.setdefault(name, {"status": "active"})
                        inferred[name]["status"] = "completed"

            return inferred

        if not rows:
            fallback_stmt = (
                live_topology_queries.get_live_topology_tool_inference_events(
                    self._dialect,
                )
            )
            try:
                fallback_rows = self.db.execute(fallback_stmt)
            except Exception:
                fallback_rows = []

            inferred_by_tool: dict[str, dict] = {}
            for row in fallback_rows:
                agent_name = str(row[0]) if row[0] else ""
                ts = str(row[1]) if row[1] else ""
                raw_agent_input = row[2]

                agent_input: object = None
                if raw_agent_input:
                    try:
                        agent_input = json.loads(str(raw_agent_input))
                    except (json.JSONDecodeError, TypeError):
                        agent_input = str(raw_agent_input)

                inferred_tools = _infer_tools_from_agent_input(
                    current_agent=agent_name,
                    payload=agent_input,
                )

                for tool_name, data in inferred_tools.items():
                    if not tool_name:
                        continue
                    if tool_name not in inferred_by_tool:
                        inferred_by_tool[tool_name] = {
                            "started_count": 0,
                            "completed_count": 0,
                            "start_time": ts,
                            "end_time": None,
                        }

                    inferred_by_tool[tool_name]["started_count"] += 1
                    if str(data.get("status") or "") == "completed":
                        inferred_by_tool[tool_name]["completed_count"] += 1
                        inferred_by_tool[tool_name]["end_time"] = ts

                    if ts and (
                        not inferred_by_tool[tool_name]["start_time"]
                        or ts > inferred_by_tool[tool_name]["start_time"]
                    ):
                        inferred_by_tool[tool_name]["start_time"] = ts

            return LiveTools(
                tools=[
                    {
                        "tool_name": tool_name,
                        "start_time": str(values["start_time"]),
                        "status": (
                            "active"
                            if _to_int(values["started_count"])
                            > _to_int(values["completed_count"])
                            else "completed"
                        ),
                        "end_time": (
                            str(values["end_time"])
                            if values["end_time"]
                            and _to_int(values["started_count"])
                            <= _to_int(values["completed_count"])
                            else None
                        ),
                    }
                    for tool_name, values in inferred_by_tool.items()
                ]
            )

        return LiveTools(
            tools=[
                {
                    "tool_name": row[0],
                    "start_time": str(row[1]),
                    "status": (
                        "active" if _to_int(row[2]) > _to_int(row[3]) else "completed"
                    ),
                    "end_time": (
                        str(row[4])
                        if row[4] and _to_int(row[2]) <= _to_int(row[3])
                        else None
                    ),
                }
                for row in rows
            ]
        )

    # ── GET /sessions/{session_id}/topology ─────────────────────────────

    def get_realtime_topology(self, *, session_id: str) -> RealtimeTopologyResponse:
        """Return a real-time topology graph built from ``otel_logs`` events.

        Processes all topology events for the session in chronological order
        to reconstruct agents (nodes), agent handoffs (edges), and tool
        invocations, along with the live status of each.
        """
        stmt = live_topology_queries.get_topology_events_by_session(
            self._dialect, session_id=session_id
        )
        try:
            rows = self.db.execute(stmt)
        except Exception as exc:
            raise DatabaseError(
                f"Failed to get topology events for session '{session_id}': {exc}"
            ) from exc

        if not rows:
            return RealtimeTopologyResponse(session_id=session_id)

        # ── Parse events chronologically ─────────────────────────────────
        session_status: str = "unknown"

        # agent_name -> tracking dict
        agent_map: dict[str, dict] = {}
        # tool_name -> tracking dict
        tool_map: dict[str, dict] = {}
        # edge_id -> edge dict (dedup by edge_id)
        edge_map: dict[str, dict] = {}

        # Stack of currently executing agents (for tool -> agent association)
        active_agent_stack: list[str] = []

        def _infer_tools_from_agent_input(
            *, current_agent: str, payload: object
        ) -> dict[str, dict[str, object]]:
            """Infer tool details from agent input message history.

            Returns a mapping of ``tool_name -> {status, input, output}``.
            """
            if not isinstance(payload, dict):
                return {}

            args = payload.get("args")
            if not isinstance(args, list) or not args:
                return {}

            first_arg = args[0]
            if not isinstance(first_arg, dict):
                return {}

            messages = first_arg.get("messages")
            if not isinstance(messages, list) or not messages:
                return {}

            decision_index: int | None = None
            for idx, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    continue
                if str(msg.get("type") or "") != "AIMessage":
                    continue
                content = msg.get("content")
                if not isinstance(content, str):
                    continue
                first_line = content.splitlines()[0].strip() if content else ""
                if not first_line.startswith("DECISION:"):
                    continue
                decided_agent = first_line.split("DECISION:", 1)[1].strip()
                if decided_agent == current_agent:
                    decision_index = idx

            if decision_index is None:
                return {}

            inferred: dict[str, dict[str, object]] = {}
            pending_by_id: dict[str, dict[str, object]] = {}

            def _normalize_input(raw: object) -> object:
                if isinstance(raw, str):
                    try:
                        return json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        return raw
                return raw

            def _extract_tool_calls(msg: dict) -> list[dict]:
                tool_calls = msg.get("tool_calls")
                if isinstance(tool_calls, list):
                    return [c for c in tool_calls if isinstance(c, dict)]

                additional_kwargs = msg.get("additional_kwargs")
                if isinstance(additional_kwargs, dict):
                    alt_calls = additional_kwargs.get("tool_calls")
                    if isinstance(alt_calls, list):
                        return [c for c in alt_calls if isinstance(c, dict)]

                return []

            def _extract_call_fields(call: dict) -> tuple[str, str, object]:
                function_obj = call.get("function")
                function_dict = function_obj if isinstance(function_obj, dict) else {}

                name = str(call.get("name") or function_dict.get("name") or "")
                call_id = str(call.get("id") or "")

                raw_input = None
                for key in (
                    "args",
                    "arguments",
                    "input",
                    "toolArguments",
                    "inputParams",
                ):
                    if call.get(key) is not None:
                        raw_input = call.get(key)
                        break

                if raw_input is None and function_dict.get("arguments") is not None:
                    raw_input = function_dict.get("arguments")

                return name, call_id, _normalize_input(raw_input)

            for msg in messages[decision_index + 1 :]:
                if not isinstance(msg, dict):
                    continue

                msg_type = str(msg.get("type") or "")
                if msg_type == "AIMessage":
                    content = msg.get("content")
                    if isinstance(content, str):
                        first_line = content.splitlines()[0].strip() if content else ""
                        if first_line.startswith("DECISION:"):
                            break

                    for call in _extract_tool_calls(msg):
                        name, call_id, inferred_input = _extract_call_fields(call)
                        if not name:
                            continue

                        effective_input = inferred_input
                        if effective_input is None and call_id:
                            effective_input = {"tool_call_id": call_id}

                        inferred.setdefault(
                            name,
                            {
                                "status": "active",
                                "input": None,
                                "output": None,
                            },
                        )

                        if inferred[name].get("input") is None:
                            inferred[name]["input"] = effective_input

                        if call_id:
                            pending_by_id[call_id] = {
                                "name": name,
                                "input": inferred[name].get("input"),
                            }

                elif msg_type == "ToolMessage":
                    name = str(msg.get("name") or "")
                    tool_call_id = str(msg.get("tool_call_id") or "")

                    if not name and tool_call_id:
                        pending = pending_by_id.get(tool_call_id)
                        if isinstance(pending, dict):
                            name = str(pending.get("name") or "")

                    if name:
                        inferred.setdefault(
                            name,
                            {
                                "status": "active",
                                "input": None,
                                "output": None,
                            },
                        )
                        if inferred[name].get("input") is None and tool_call_id:
                            pending = pending_by_id.get(tool_call_id)
                            if isinstance(pending, dict):
                                inferred[name]["input"] = pending.get("input")
                            else:
                                inferred[name]["input"] = {"tool_call_id": tool_call_id}
                        inferred[name]["status"] = "completed"
                        inferred[name]["output"] = msg.get("content")

            return inferred

        for row in rows:
            event_name = str(row[0]) if row[0] else ""
            agent_name = str(row[1]) if row[1] else ""
            tool_name = str(row[2]) if row[2] else ""
            source_agent = str(row[3]) if row[3] else ""
            target_agent = str(row[4]) if row[4] else ""
            ev_edge_id = str(row[5]) if row[5] else ""
            ev_edge_kind = str(row[6]) if row[6] else ""
            ts = str(row[8]) if row[8] else ""
            raw_agent_input = row[9]
            raw_tool_input = row[10]
            raw_tool_output = row[11]

            # Parse JSON input fields — they are stored as JSON strings
            agent_input: object = None
            if raw_agent_input:
                try:
                    agent_input = json.loads(str(raw_agent_input))
                except (json.JSONDecodeError, TypeError):
                    agent_input = str(raw_agent_input)

            tool_input: object = None
            if raw_tool_input:
                try:
                    tool_input = json.loads(str(raw_tool_input))
                except (json.JSONDecodeError, TypeError):
                    tool_input = str(raw_tool_input)

            tool_output: object = None
            if raw_tool_output:
                try:
                    tool_output = json.loads(str(raw_tool_output))
                except (json.JSONDecodeError, TypeError):
                    tool_output = str(raw_tool_output)

            if event_name == "topology.session.started":
                session_status = "active"

            elif event_name == "topology.session.completed":
                session_status = "completed"

            elif event_name == "topology.node.started" and agent_name:
                if agent_name not in agent_map:
                    agent_map[agent_name] = {
                        "status": "active",
                        "start_time": ts,
                        "end_time": None,
                        "tools": [],
                        "input": agent_input,
                    }
                else:
                    # Agent re-entered (multiple invocations in session)
                    agent_map[agent_name]["status"] = "active"
                    agent_map[agent_name]["start_time"] = ts
                    agent_map[agent_name]["end_time"] = None
                    agent_map[agent_name]["input"] = agent_input
                active_agent_stack.append(agent_name)

            elif event_name == "topology.node.completed" and agent_name:
                if agent_name not in agent_map:
                    agent_map[agent_name] = {
                        "status": "completed",
                        "start_time": None,
                        "end_time": ts,
                        "tools": [],
                        "input": None,
                    }
                else:
                    agent_map[agent_name]["status"] = "completed"
                    agent_map[agent_name]["end_time"] = ts

                # Pop last occurrence from active stack
                for i in range(len(active_agent_stack) - 1, -1, -1):
                    if active_agent_stack[i] == agent_name:
                        active_agent_stack.pop(i)
                        break

            elif (
                event_name == "topology.edge.updated"
                and ev_edge_id
                and source_agent
                and target_agent
            ):
                # Deduplicate by edge_id — keep first observed occurrence
                if ev_edge_id not in edge_map:
                    edge_map[ev_edge_id] = {
                        "source": source_agent,
                        "target": target_agent,
                        "label": ev_edge_kind or "agent_handoff",
                    }

            elif event_name == "tool.started" and tool_name:
                cur_agent = active_agent_stack[-1] if active_agent_stack else None
                if tool_name not in tool_map:
                    tool_map[tool_name] = {
                        "status": "active",
                        "start_time": ts,
                        "end_time": None,
                        "input": tool_input,
                        "output": None,
                    }
                else:
                    tool_map[tool_name]["status"] = "active"
                    tool_map[tool_name]["start_time"] = ts
                    tool_map[tool_name]["end_time"] = None
                    if tool_input is not None:
                        tool_map[tool_name]["input"] = tool_input
                # Associate tool with active agent and add a directed edge
                if cur_agent and cur_agent in agent_map:
                    if tool_name not in agent_map[cur_agent]["tools"]:
                        agent_map[cur_agent]["tools"].append(tool_name)
                    # Add agent -> tool edge (dedup by composite key)
                    tool_edge_id = f"tool_invocation:{cur_agent}->{tool_name}"
                    if tool_edge_id not in edge_map:
                        edge_map[tool_edge_id] = {
                            "source": cur_agent,
                            "target": tool_name,
                            "label": "tool_invocation",
                        }

            elif event_name == "tool.completed" and tool_name:
                if tool_name not in tool_map:
                    tool_map[tool_name] = {
                        "status": "completed",
                        "start_time": None,
                        "end_time": ts,
                        "input": tool_input,
                        "output": tool_output,
                    }
                else:
                    tool_map[tool_name]["status"] = "completed"
                    tool_map[tool_name]["end_time"] = ts
                    if (
                        tool_input is not None
                        and tool_map[tool_name].get("input") is None
                    ):
                        tool_map[tool_name]["input"] = tool_input
                    if tool_output is not None:
                        tool_map[tool_name]["output"] = tool_output

        # Fallback: infer tool invocations from agent input payloads for traces
        # where explicit tool.started/tool.completed events are not emitted.
        for agent_name, data in agent_map.items():
            inferred_tools = _infer_tools_from_agent_input(
                current_agent=agent_name,
                payload=data.get("input"),
            )
            for inferred_tool, inferred_data in inferred_tools.items():
                if inferred_tool not in data["tools"]:
                    data["tools"].append(inferred_tool)

                if inferred_tool not in tool_map:
                    tool_map[inferred_tool] = {
                        "status": str(inferred_data.get("status") or "active"),
                        "start_time": None,
                        "end_time": None,
                        "input": inferred_data.get("input"),
                        "output": inferred_data.get("output"),
                    }
                elif (
                    str(inferred_data.get("status") or "") == "completed"
                    and tool_map[inferred_tool]["status"] != "completed"
                ):
                    tool_map[inferred_tool]["status"] = "completed"
                if (
                    inferred_data.get("input") is not None
                    and tool_map[inferred_tool].get("input") is None
                ):
                    tool_map[inferred_tool]["input"] = inferred_data.get("input")
                if inferred_data.get("output") is not None:
                    tool_map[inferred_tool]["output"] = inferred_data.get("output")

                tool_edge_id = f"tool_invocation:{agent_name}->{inferred_tool}"
                if tool_edge_id not in edge_map:
                    edge_map[tool_edge_id] = {
                        "source": agent_name,
                        "target": inferred_tool,
                        "label": "tool_invocation",
                    }

        # ── Build response ────────────────────────────────────────────────
        nodes: list[RealtimeTopologyNode] = []

        for name, data in agent_map.items():
            node_data: object = {
                "input": data["input"],
                "tools": data["tools"] or [],
            }
            nodes.append(
                RealtimeTopologyNode(
                    id=name,
                    name=name,
                    type="agent",
                    status=data["status"],
                    start_time=data["start_time"],
                    end_time=data["end_time"],
                    data=node_data,
                )
            )

        for name, data in tool_map.items():
            node_data = {"input": data.get("input"), "output": data.get("output")}
            nodes.append(
                RealtimeTopologyNode(
                    id=name,
                    name=name,
                    type="tool",
                    status=data["status"],
                    start_time=data["start_time"],
                    end_time=data["end_time"],
                    data=node_data,
                )
            )

        edges: list[RealtimeTopologyEdge] = [
            RealtimeTopologyEdge(
                source=e["source"],
                target=e["target"],
                label=e["label"],
            )
            for e in edge_map.values()
        ]

        return RealtimeTopologyResponse(
            session_id=session_id,
            session_status=session_status,  # type: ignore[arg-type]
            nodes=nodes,
            edges=edges,
            last_updated=datetime.now(tz=timezone.utc).isoformat(),
        )
