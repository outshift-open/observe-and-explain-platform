#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""OXPKGProvider — Neo4j-backed KGProvider + DataProvider.

Handles all knowledge-graph read operations: generic node queries,
session / agent / LLM-call listings, and execution-span fetching for
the MCE computation engine.

All Cypher is centralised in ``oxp.query_builders.kg``.  No raw
query strings live in this file.

Query execution uses an ontology-first / workaround-fallback strategy
governed by :class:`~oxp.workarounds.KGWorkaroundsConfig`.  See
``oxp/workarounds.py`` for the full workaround catalogue.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import replace
from typing import Any

from oxp.connectors.base import Connector
from oxp.interfaces import DataProvider, KGProvider
from oxp.interfaces.models import QueryOptions, RetrievalRequest, RetrievalScope
from oxp.query_builders import kg as kg_qb

logger = logging.getLogger(__name__)

# Valid Neo4j node label: starts with letter or underscore, alphanumeric + underscore only.
_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _resolve_connector(
    db: Connector | None,
    connector: Connector | None,
    *,
    host: str | None = None,
    username: str | None = None,
    password: str | None = None,
    database: str | None = None,
) -> Connector:
    """Return the supplied connector, or build one from environment variables."""
    resolved = db or connector
    if resolved is None:
        from oxp.connectors.neo4j import Neo4JConnector
        from oxp.core.config import resolve_neo4j_auth

        resolved_host = (
            host or os.getenv("NEO4J_HOST") or os.getenv("KG_DB_HOST") or "localhost"
        )
        if ":" in resolved_host and not resolved_host.startswith("bolt://"):
            hostname, _, port_str = resolved_host.rpartition(":")
            try:
                port = int(port_str)
            except ValueError:
                hostname, port = resolved_host, 7687
        else:
            hostname, port = resolved_host, 7687
        default_username, default_password = resolve_neo4j_auth()
        resolved = Neo4JConnector(
            host=hostname,
            port=port,
            username=(username or os.getenv("KG_DB_USER") or default_username),
            password=(password or os.getenv("KG_DB_PASSWORD") or default_password),
            database=database
            or os.getenv("NEO4J_DATABASE")
            or os.getenv("KG_DB_NAME")
            or "neo4j",
        )
    resolved.ensure_connected()
    return resolved


class OXPKGProvider(KGProvider, DataProvider):
    """Neo4j-backed KGProvider + DataProvider.

    *KGProvider* — generic node queries, session / agent / LLM-call listings.
    *DataProvider* — execution-span fetching (``fetch``, ``resolve_session_id``)
    used by the MCE computation engine.
    """

    def __init__(
        self,
        db: Connector | None = None,
        *,
        connector: Connector | None = None,
        host: str | None = None,
        username: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        """Accept ``db=`` (canonical) or ``connector=`` (compat alias)."""
        self._db = _resolve_connector(
            db,
            connector,
            host=host,
            username=username,
            password=password,
            database=database,
        )

    # ── KGProvider ────────────────────────────────────────────────────────

    def query_nodes(
        self,
        entity_type: str,
        options: QueryOptions | None = None,
    ) -> list[dict[str, Any]]:
        """Query KG nodes by label with SQL-like filters, projection, and ordering.

        ``entity_type`` must be a valid Neo4j label (alphanumeric / underscore)
        or ``"*"`` to match all nodes.  Invalid labels raise ``ValueError``
        rather than silently injecting Cypher.
        """
        if entity_type and entity_type != "*" and not _LABEL_RE.match(entity_type):
            raise ValueError(f"Invalid entity_type label: {entity_type!r}")

        options = options or QueryOptions()
        label_part = f":{entity_type}" if entity_type and entity_type != "*" else ""
        clauses = [f"MATCH (n{label_part})"]
        params: dict[str, Any] = {}
        where_parts: list[str] = []

        if options.filters:
            for k, v in options.filters.items():
                pk = f"filter_{k}"
                where_parts.append(
                    f"n.{k} IN ${pk}" if isinstance(v, list) else f"n.{k} = ${pk}"
                )
                params[pk] = v

        if options.where_clause:
            # NOTE: where_clause is an internal escape-hatch for trusted callers only.
            # It is not exposed over HTTP and must never receive user-supplied strings.
            wc = options.where_clause.strip()
            if wc.lower().startswith("where"):
                wc = wc[5:].strip()
            where_parts.append(f"({wc})")

        if where_parts:
            clauses.append("WHERE " + " AND ".join(where_parts))

        if options.columns and options.columns != ["*"]:
            ret_parts = [
                col
                if ("(" in col or " AS " in col.upper() or "." in col)
                else f"n.{col} AS {col}"
                for col in options.columns
            ]
            clauses.append("RETURN " + ", ".join(ret_parts))
        else:
            clauses.append("RETURN n")

        if options.order_by:
            sort_parts = []
            for field in options.order_by:
                desc = field.startswith("-")
                f_clean = field.lstrip("-")
                if "." not in f_clean:
                    f_clean = f"n.{f_clean}"
                sort_parts.append(f"{f_clean} {'DESC' if desc else 'ASC'}")
            clauses.append("ORDER BY " + ", ".join(sort_parts))

        if options.limit:
            clauses.append(f"LIMIT {int(options.limit)}")

        try:
            return self._db.execute("\n".join(clauses), params) or []
        except Exception as exc:
            logger.error("query_nodes(%s) failed: %s", entity_type, exc)
            return []

    def list_sessions(self, limit: int = 100) -> list[dict[str, Any]]:
        """List sessions ordered by most recent first."""
        query, params = kg_qb.list_sessions_query(limit)
        try:
            return self._db.execute(query, params) or []
        except Exception as exc:
            logger.error("list_sessions failed: %s", exc)
            return []

    def list_agents(self, session_id: str) -> list[dict[str, Any]]:
        """List AgentCall nodes for a session, with their Agent's real name."""
        try:
            return self._db.execute(*kg_qb.list_agents_query(session_id)) or []
        except Exception as exc:
            logger.error("list_agents failed: %s", exc)
            return []

    def list_llm_calls(self, session_id: str) -> list[dict[str, Any]]:
        """List LLMCall nodes for a session, with their LLM's real name."""
        try:
            return self._db.execute(*kg_qb.list_llm_calls_query(session_id)) or []
        except Exception as exc:
            logger.error("list_llm_calls failed: %s", exc)
            return []

    # ── DataProvider ──────────────────────────────────────────────────────

    def resolve_session_id(self, resource_id: str) -> str | None:
        """Resolve any resource ID to its parent Session ID."""
        for query, params in kg_qb.resolve_session_id_queries(resource_id):
            try:
                rows = self._db.execute(query, params)
                if rows and rows[0].get("sid"):
                    return rows[0]["sid"]
            except Exception as exc:
                logger.debug("resolve_session_id query failed: %s", exc)
        return None

    def retrieve(self, request: RetrievalRequest) -> dict[str, Any]:
        """Execute a faceted retrieval request.

        This V1 implementation supports declarative session scoping, ordered
        AgentCall sequence retrieval, basic client-side filtering/ordering, and
        simple aggregates such as counts.
        """
        session_ids = self._resolve_scope_session_ids(request)
        contexts: dict[str, dict[str, Any]] = {}

        for session_id in session_ids:
            context: dict[str, Any] = {"session_id": session_id}

            for node in request.nodes:
                alias = node.alias or self._context_key_for_entity(node.entity_type)
                records = self._retrieve_node_records(session_id, node, request)
                if node.limit is not None:
                    records = records[: node.limit]

                if self._context_key_for_entity(node.entity_type) == "session":
                    context[alias] = records[0] if records else {}
                else:
                    context[alias] = records

            self._apply_aggregates(context, request)
            contexts[session_id] = context

        return {
            "session_ids": session_ids,
            "contexts": contexts,
        }

    def fetch(self, resource_id: str, requirements: Any) -> dict[str, Any]:
        """Fetch execution spans from Neo4j for metric computation.

        Returns a dict with keys: session_id, session, agent_spans, llm_spans,
        tool_spans, conversation, conversation_data, input_text, output_text.
        """
        try:
            retrieval_request = requirements.retrieval
        except AttributeError:
            retrieval_request = None
        if retrieval_request is not None:
            request = self._anchor_request(retrieval_request, resource_id)
            retrieved = self.retrieve(request)
            contexts = retrieved.get("contexts", {})
            session_ids = retrieved.get("session_ids", [])
            session_id = (
                resource_id
                if resource_id in contexts
                else (session_ids[0] if session_ids else None)
            )
            return contexts.get(session_id, {}) if session_id is not None else {}

        # 1. Main record (session + its AgentCall/LLMCall/ToolCall/ProcessingCall descendants)
        try:
            rows = self._db.execute(*kg_qb.fetch_session_query(resource_id))
        except Exception as exc:
            logger.warning("fetch_session failed for %s: %s", resource_id, exc)
            rows = None
        record = rows[0] if rows else None

        if record is None:
            logger.warning("Session %s not found in Neo4j", resource_id)
            return {}

        session_node = record.get("s") or {}
        session_props = (
            dict(session_node.items())
            if hasattr(session_node, "items")
            else dict(session_node)
        )

        # 2. Session timing (Session is always populated with startTime/duration
        #    directly, but keep this as a defensive top-up).
        try:
            timing_rows = self._db.execute(
                *kg_qb.fetch_session_timing_query(resource_id)
            )
        except Exception as exc:
            logger.debug("fetch_session_timing failed for %s: %s", resource_id, exc)
            timing_rows = None
        if timing_rows:
            t = timing_rows[0]
            if t.get("startTime") is not None:
                session_props.setdefault("startTime", t["startTime"])
            if t.get("duration") is not None:
                session_props.setdefault("duration", t["duration"])

        def _as_dict(n: Any) -> dict[str, Any]:
            return dict(n.items()) if hasattr(n, "items") else dict(n)

        agent_call_nodes = [_as_dict(n) for n in (record.get("agent_calls") or []) if n]
        llm_call_nodes = [_as_dict(n) for n in (record.get("llm_calls") or []) if n]
        tool_call_nodes = [_as_dict(n) for n in (record.get("tool_calls") or []) if n]

        all_ids = [
            n["id"]
            for n in (*agent_call_nodes, *llm_call_nodes, *tool_call_nodes)
            if n.get("id")
        ]
        enrichment = self._fetch_enrichment(all_ids)

        agent_spans = [
            self._normalize_agent_call(n, enrichment=enrichment.get(n.get("id")))
            for n in agent_call_nodes
        ]
        llm_spans = [
            self._normalize_llm_call(n, enrichment=enrichment.get(n.get("id")))
            for n in llm_call_nodes
        ]
        tool_spans = [
            self._normalize_tool_call(n, enrichment=enrichment.get(n.get("id")))
            for n in tool_call_nodes
        ]

        # 3. Conversation data: the session's own turn, falling back to the
        #    first/last AgentCall's own turn, then the first/last LLMCall's.
        try:
            conv_rows = self._db.execute(*kg_qb.fetch_conversation_query(resource_id))
        except Exception as exc:
            logger.debug("fetch_conversation failed for %s: %s", resource_id, exc)
            conv_rows = None
        conv_row = conv_rows[0] if conv_rows else {}
        input_text = conv_row.get("input") or ""
        output_text = conv_row.get("output") or ""

        if not input_text or not output_text:
            fallback_input, fallback_output = self._derive_session_query_response(
                agent_spans, llm_spans
            )
            input_text = input_text or fallback_input
            output_text = output_text or fallback_output

        conversation_data = {"query": input_text, "response": output_text}
        conversation = (
            f"User: {input_text}\nAssistant: {output_text}".strip()
            if input_text or output_text
            else ""
        )

        return {
            "session_id": resource_id,
            "session": session_props,
            "agent_spans": agent_spans,
            "llm_spans": llm_spans,
            "tool_spans": tool_spans,
            "conversation": conversation,
            "conversation_data": conversation_data,
            "input_text": input_text,
            "output_text": output_text,
        }

    def _fetch_enrichment(self, call_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Batch-fetch structural name/provider + own initial/final State
        content for every call id, keyed by id."""
        if not call_ids:
            return {}
        try:
            rows = self._db.execute(*kg_qb.fetch_call_content_and_names_query(call_ids))
        except Exception as exc:
            logger.debug("fetch_call_content_and_names failed: %s", exc)
            return {}
        return {row["id"]: dict(row) for row in (rows or []) if row.get("id")}

    def _resolve_scope_session_ids(self, request: RetrievalRequest) -> list[str]:
        session_ids: list[str] = []

        for session_id in request.scope.session_ids:
            if session_id not in session_ids:
                session_ids.append(session_id)

        for resource_id in request.scope.resource_ids:
            session_id = self.resolve_session_id(resource_id)
            if session_id and session_id not in session_ids:
                session_ids.append(session_id)

        if request.scope.start_time is not None or request.scope.end_time is not None:
            query, params = kg_qb.list_sessions_in_interval_query(
                request.scope.start_time,
                request.scope.end_time,
                request.limit,
            )
            rows = self._db.execute(query, params) or []
            for row in rows:
                session_id = row.get("session_id")
                if session_id and session_id not in session_ids:
                    session_ids.append(session_id)

        return session_ids

    def _anchor_request(
        self, request: RetrievalRequest, resource_id: str
    ) -> RetrievalRequest:
        if request.scope.session_ids or request.scope.resource_ids:
            return request

        session_id = self.resolve_session_id(resource_id) or resource_id
        return replace(
            request,
            scope=RetrievalScope(session_ids=[session_id]),
        )

    @staticmethod
    def _context_key_for_entity(entity_type: str) -> str:
        mapping = {
            "mas:AgentCall": "agent_calls",
            "AgentCall": "agent_calls",
            "mas:LLMCall": "llm_calls",
            "LLMCall": "llm_calls",
            "mas:ToolCall": "tool_calls",
            "ToolCall": "tool_calls",
            "mas:MASCall": "mas_calls",
            "MASCall": "mas_calls",
            "mas:Session": "session",
            "Session": "session",
        }
        return mapping.get(entity_type, entity_type.split(":")[-1].lower())

    def _retrieve_node_records(
        self, session_id: str, node: Any, request: RetrievalRequest
    ) -> list[dict[str, Any]]:
        try:
            rows = (
                self._db.execute(
                    *kg_qb.fetch_traversed_nodes_query(
                        session_id,
                        node.entity_type,
                        request.edges,
                        order_by=node.order_by or request.order_by,
                    )
                )
                or []
            )
        except Exception as exc:
            logger.debug(
                "retrieve_%s failed for %s: %s",
                self._context_key_for_entity(node.entity_type),
                session_id,
                exc,
            )
            rows = []

        node_dicts = [self._as_dict(row["node"]) for row in rows if row.get("node")]
        enrichment = self._fetch_enrichment(
            [n["id"] for n in node_dicts if n.get("id")]
        )

        records = [
            self._normalize_entity(
                node.entity_type, n, enrichment=enrichment.get(n.get("id"))
            )
            for n in node_dicts
        ]
        records = self._apply_filters(records, node.filters)
        records = self._sort_records(
            records,
            node.order_by
            or request.order_by
            or self._default_order_for_entity(node.entity_type),
        )
        if node.fields:
            records = [self._project_fields(record, node.fields) for record in records]
        return records

    @staticmethod
    def _project_fields(record: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        return {field: record.get(field) for field in fields}

    @staticmethod
    def _default_order_for_entity(entity_type: str) -> list[str]:
        key = entity_type.split(":")[-1]
        if key in {"AgentCall", "LLMCall", "ToolCall", "MASCall"}:
            return ["startTime"]
        return []

    def _normalize_entity(
        self,
        entity_type: str,
        node: dict[str, Any],
        *,
        enrichment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        key = entity_type.split(":")[-1]
        if key == "ToolCall":
            return self._normalize_tool_call(node, enrichment=enrichment)
        if key == "LLMCall":
            return self._normalize_llm_call(node, enrichment=enrichment)
        if key == "AgentCall":
            return self._normalize_agent_call(node, enrichment=enrichment)
        return node

    @staticmethod
    def _apply_filters(
        records: list[dict[str, Any]], filters: dict[str, Any]
    ) -> list[dict[str, Any]]:
        if not filters:
            return records

        filtered: list[dict[str, Any]] = []
        for record in records:
            keep = True
            for key, expected in filters.items():
                value = record.get(key)
                if isinstance(expected, list):
                    if value not in expected:
                        keep = False
                        break
                elif value != expected:
                    keep = False
                    break
            if keep:
                filtered.append(record)
        return filtered

    @staticmethod
    def _sort_records(
        records: list[dict[str, Any]], order_by: list[str]
    ) -> list[dict[str, Any]]:
        if not order_by:
            return records

        sorted_records = list(records)
        for field in reversed(order_by):
            descending = field.startswith("-")
            field_name = field.lstrip("-")
            sorted_records.sort(
                key=lambda record: (
                    record.get(field_name) is None,
                    record.get(field_name),
                ),
                reverse=descending,
            )
        return sorted_records

    def _apply_aggregates(
        self, context: dict[str, Any], request: RetrievalRequest
    ) -> None:
        for aggregate in request.aggregates:
            alias = aggregate.alias or aggregate.function
            if aggregate.function != "count" or not aggregate.entity_type:
                raise NotImplementedError(
                    f"Unsupported aggregate facet: {aggregate.function!r}"
                )

            key = self._context_key_for_entity(aggregate.entity_type)
            records = context.get(key, [])
            if aggregate.group_by:
                grouped: dict[Any, int] = {}
                for record in records:
                    group_key = tuple(record.get(field) for field in aggregate.group_by)
                    normalized_key = group_key[0] if len(group_key) == 1 else group_key
                    grouped[normalized_key] = grouped.get(normalized_key, 0) + 1
                context[alias] = grouped
            else:
                context[alias] = len(records)

    @staticmethod
    def _as_dict(node: Any) -> dict[str, Any]:
        return dict(node.items()) if hasattr(node, "items") else dict(node)

    @staticmethod
    def _derive_session_query_response(
        agent_spans: list[dict[str, Any]],
        llm_spans: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Fall back to the first/last AgentCall's own turn, then the
        first/last LLMCall's, when the session has no conversation State of
        its own."""

        def _pick_first(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
            for key in keys:
                value = mapping.get(key)
                if value not in (None, ""):
                    return str(value)
            return ""

        query = ""
        for agent_call in agent_spans:
            query = _pick_first(agent_call, ("inputContent",))
            if query:
                break
        if not query:
            for llm_call in llm_spans:
                query = _pick_first(llm_call, ("prompt", "inputContent"))
                if query:
                    break

        response = ""
        for agent_call in reversed(agent_spans):
            response = _pick_first(agent_call, ("outputContent",))
            if response:
                break
        if not response:
            for llm_call in reversed(llm_spans):
                response = _pick_first(llm_call, ("completion", "outputContent"))
                if response:
                    break

        return query, response

    # ── normalizers ───────────────────────────────────────────────────────
    #
    # Each takes the raw call node plus the batched enrichment row for its id
    # (structural name/provider + own initial/final State content -- see
    # kg_qb.fetch_call_content_and_names_query) and produces the field names
    # downstream MCE metrics already expect (toolName/inputContent/
    # outputContent/prompt/completion/contains_error/...).

    @staticmethod
    def _normalize_tool_call(
        node: dict[str, Any],
        *,
        enrichment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(node)
        enrichment = enrichment or {}

        tool_name = enrichment.get("name")
        if tool_name:
            normalized["toolName"] = tool_name

        input_content = enrichment.get("inputContent")
        if input_content is not None:
            normalized["inputContent"] = input_content
            normalized["toolArguments"] = input_content
            normalized["inputParams"] = input_content

        output_content = enrichment.get("outputContent")
        if output_content is not None:
            normalized["outputContent"] = output_content
            normalized["toolOutput"] = output_content

        normalized["contains_error"] = normalized.get("success") is False
        return normalized

    @staticmethod
    def _normalize_llm_call(
        node: dict[str, Any],
        *,
        enrichment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(node)
        enrichment = enrichment or {}

        model_name = enrichment.get("name")
        if model_name:
            normalized["modelName"] = model_name
            normalized["llmName"] = model_name
        provider = enrichment.get("provider")
        if provider:
            normalized["provider"] = provider

        input_content = enrichment.get("inputContent")
        if input_content is not None:
            normalized["inputContent"] = input_content
            normalized["prompt"] = input_content

        output_content = enrichment.get("outputContent")
        if output_content is not None:
            normalized["outputContent"] = output_content
            normalized["completion"] = output_content

        normalized["contains_error"] = normalized.get("success") is False
        return normalized

    @staticmethod
    def _normalize_agent_call(
        node: dict[str, Any],
        *,
        enrichment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized = dict(node)
        enrichment = enrichment or {}

        agent_name = enrichment.get("name")
        if agent_name:
            normalized["agentName"] = agent_name

        input_content = enrichment.get("inputContent")
        if input_content is not None:
            normalized["inputContent"] = input_content

        output_content = enrichment.get("outputContent")
        if output_content is not None:
            normalized["outputContent"] = output_content

        normalized["contains_error"] = normalized.get("success") is False
        return normalized
