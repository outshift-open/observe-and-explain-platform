#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
"""Unit tests for the top-level normalize()/Normalizer API."""

from __future__ import annotations

import json

from norm import Normalizer, StreamDelta, configure, normalize


def test_normalize_invokes_configured_callback() -> None:
    calls = []
    configure(on_normalized=lambda spans, nodes, edges: calls.append((spans, nodes, edges)))
    try:
        spans = [_agent_span()]
        nodes, edges = normalize(spans)
    finally:
        configure(on_normalized=None)
    assert calls == [(spans, nodes, edges)]


def _agent_span(session_id: str = "sess-1") -> dict:
    return {
        "Timestamp": "2026-07-09 12:00:00.000000000",
        "SpanId": "span-1",
        "ParentSpanId": "",
        "SpanName": "concierge.agent",
        "Duration": 1_000_000_000,
        "SpanAttributes": {
            "application_id": "app",
            "session.id": f"app_{session_id}",
            "agent_id": "concierge",
        },
    }


def test_normalize_returns_nodes_and_edges() -> None:
    nodes, edges = normalize([_agent_span()])
    assert any(node.get("node_type") == "AgentCall" for node in nodes)
    assert edges


def test_success_propagates_from_execution_success_attribute() -> None:
    span = _agent_span()
    span["SpanAttributes"]["execution.success"] = "true"
    nodes, _edges = normalize([span])
    agent_call = next(n for n in nodes if n["node_type"] == "AgentCall")
    assert agent_call["success"] is True


def test_success_defaults_true_when_span_carries_no_signal() -> None:
    nodes, _edges = normalize([_agent_span()])
    agent_call = next(n for n in nodes if n["node_type"] == "AgentCall")
    assert agent_call["success"] is True


def test_success_is_false_on_explicit_error_status_code() -> None:
    span = _agent_span()
    span["StatusCode"] = "Error"
    nodes, _edges = normalize([span])
    agent_call = next(n for n in nodes if n["node_type"] == "AgentCall")
    assert agent_call["success"] is False


def test_normalizer_process_file_matches_normalize(tmp_path) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text(json.dumps(_agent_span()) + "\n", encoding="utf-8")

    nodes, edges = Normalizer().process_file(path)
    expected_nodes, expected_edges = normalize([_agent_span()])
    assert len(nodes) == len(expected_nodes)
    assert len(edges) == len(expected_edges)


def test_normalizer_process_file_json_returns_flat_list(tmp_path) -> None:
    path = tmp_path / "spans.jsonl"
    path.write_text(json.dumps(_agent_span()) + "\n", encoding="utf-8")

    flat = Normalizer().process_file_json(path)
    nodes, edges = normalize([_agent_span()])
    assert len(flat) == len(nodes) + len(edges)


def test_stream_normalizer_converges_to_batch_result() -> None:
    from pathlib import Path

    from norm import InMemoryGraph, StreamNormalizer
    from norm.normalizer import load_json

    fixture = Path(__file__).resolve().parent / "fixtures" / "noa_trip_planner.otel_export.jsonl"
    spans = load_json(fixture)

    graph = InMemoryGraph()
    for span in spans:
        # A brand-new normalizer per span: nothing is kept in memory between spans.
        graph.apply(StreamNormalizer(graph).process(span))

    batch_nodes, batch_edges = normalize(spans)
    assert {i for _, i in graph.nodes} == {n["id"] for n in batch_nodes}
    assert set(graph.edges) == {(e["edge_type"], e["from_id"], e["to_id"]) for e in batch_edges}


def test_stream_normalizer_ignores_already_processed_span() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    graph.apply(StreamNormalizer(graph).process(_agent_span()))
    assert StreamNormalizer(graph).process(_agent_span()) == StreamDelta()


def test_stream_normalizer_kind_event_dispatches_by_name(capsys) -> None:
    import pytest

    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    delta = StreamNormalizer(graph).process(
        {"LogAttributes": {"event.name": "llm.started"}}, kind="event"
    )
    assert delta == StreamDelta()
    capsys.readouterr()
    assert not graph.nodes

    # "span" is the default and still normalizes the span
    delta = StreamNormalizer(graph).process(_agent_span())
    assert delta.nodes
    assert "llm.started" not in capsys.readouterr().out

    with pytest.raises(ValueError):
        StreamNormalizer(graph).process(_agent_span(), kind="metric")  # type: ignore[arg-type]


def _session_started_event() -> dict:
    return {
        "Timestamp": "2026-10-15 14:50:46.939986688",
        "SpanId": "211fdd62f03f330c",
        "ServiceName": "noa-trip-planner-mas",
        "Body": "topology.session.started",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": "topology.session.started",
            "event.time": "2026-10-15T14:50:46.938750+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "snapshot.version": "1",
        },
    }


def test_topology_session_started_creates_session_and_mas() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    delta = normalizer.process(_session_started_event(), kind="event")
    graph.apply(delta)

    assert sorted(n["node_type"] for n in delta.nodes) == ["MAS", "Session", "State"]
    session = graph.nodes[("Session", "213dad2f")]
    assert session["startTime"] == 1792075846.93875
    assert session["spanId"] == "211fdd62f03f330c"
    assert sorted(e["edge_type"] for e in delta.edges) == [
        "executesSession", "hasInitialState", "hasState"
    ]
    assert not any(e["edge_type"] == "hasFinalState" for e in delta.edges)

    # re-delivery changes nothing
    assert normalizer.process(_session_started_event(), kind="event") == StreamDelta()


def test_topology_session_started_without_session_id_is_noop() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    event = _session_started_event()
    del event["LogAttributes"]["session.id"]
    assert StreamNormalizer(InMemoryGraph()).process(event, kind="event") == StreamDelta()



def _node_event(name: str, **extra: str) -> dict:
    return {
        "Timestamp": "2026-10-15 14:50:46.959707000",
        "SpanId": "427bddeaf7b098f0",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": name,
            "event.time": "2026-10-15T14:50:46.959707+00:00" if name.endswith("started") else "2026-10-15T14:50:48.500603+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "agent.name": "moderator",
            **extra,
        },
    }


def test_topology_node_events_build_agent_call_states_and_transition() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    for event in (
        _node_event("topology.node.started", **{"agent.input": "hello"}),
        _node_event("topology.node.completed", **{"agent.output": "bye"}),
    ):
        graph.apply(normalizer.process(event, kind="event"))

    types = sorted(t for t, _ in graph.nodes)
    assert types == ["Agent", "AgentCall", "MAS", "MASCall", "Session", "State", "State", "Transition"]
    contents = sorted(n["content"] for (t, _), n in graph.nodes.items() if t == "State")
    assert contents == ["bye", "hello"]
    edge_types = {e["edge_type"] for e in graph.edges.values()}
    assert {"hasInitialState", "hasFinalState", "inputTo", "leadsTo", "executesAgent", "hasAgentCall"} <= edge_types

    call = next(n for (t, _), n in graph.nodes.items() if t == "AgentCall")
    assert call["endTime"] > call["startTime"]
    assert call["duration"] > 0

    # re-delivery changes nothing
    assert normalizer.process(_node_event("topology.node.completed", **{"agent.output": "bye"}), kind="event") == StreamDelta()


def test_topology_node_completed_alone_creates_everything() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    delta = StreamNormalizer(graph).process(
        _node_event("topology.node.completed", **{"agent.output": "bye"}), kind="event"
    )
    graph.apply(delta)
    states = sorted(n["content"] for (t, _), n in graph.nodes.items() if t == "State")
    assert states == ["(no content recorded)", "bye"]
    assert ("Transition", next(i for t, i in graph.nodes if t == "Transition")) in graph.nodes


def test_topology_session_completed_creates_missing_nodes_and_final_state() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    started = _session_started_event()
    completed = {
        "Timestamp": "2026-10-15 14:56:13.324206336",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            **started["LogAttributes"],
            "event.name": "topology.session.completed",
            "event.time": "2026-10-15T14:56:13.322348+00:00",
        },
    }
    # completed alone creates everything started does, plus the states/transition
    graph.apply(normalizer.process(completed, kind="event"))
    types = sorted(t for t, _ in graph.nodes)
    assert types == ["MAS", "Session", "State", "State", "Transition"]
    edge_types = {e["edge_type"] for e in graph.edges.values()}
    assert {"executesSession", "hasInitialState", "hasFinalState", "inputTo", "leadsTo"} <= edge_types
    assert normalizer.process(completed, kind="event") == StreamDelta()

    # started afterwards adds nothing; started-then-completed ends the session later
    assert normalizer.process(started, kind="event") == StreamDelta()
    graph2 = InMemoryGraph()
    n2 = StreamNormalizer(graph2)
    graph2.apply(n2.process(started, kind="event"))
    graph2.apply(n2.process(completed, kind="event"))
    session = graph2.nodes[("Session", "213dad2f")]
    assert session["endTime"] > session["startTime"] and session["duration"] > 0
    assert sorted(t for t, _ in graph2.nodes) == types



def _session_completed(time: str) -> dict:
    started = _session_started_event()
    return {
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            **started["LogAttributes"],
            "event.name": "topology.session.completed",
            "event.time": time,
        },
    }


def _final_states(graph) -> list[str]:
    return sorted(e["to_id"] for e in graph.edges.values() if e["edge_type"] == "hasFinalState")


def test_only_the_latest_session_completed_has_final_state() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    early = _session_completed("2026-10-15T14:56:13+00:00")
    late = _session_completed("2026-10-15T14:56:18+00:00")
    session_edges = lambda g, t: [e for e in g.edges.values() if e["edge_type"] == t and e["from_id"] == "213dad2f"]

    # in order: the final State moves to the later event, the earlier State stays attached
    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    for event in (_session_started_event(), early):
        graph.apply(normalizer.process(event, kind="event"))
    first_final = _final_states(graph)
    assert len(first_final) == 1
    graph.apply(normalizer.process(late, kind="event"))
    assert len(_final_states(graph)) == 1 and _final_states(graph) != first_final
    assert len(session_edges(graph, "hasInitialState")) == 1
    assert len(session_edges(graph, "hasState")) == 3  # initial + one per completion
    assert graph.nodes[("Session", "213dad2f")]["endTime"] == 1792076178.0

    # out of order: the earlier event arriving last does not take the final State back
    graph2 = InMemoryGraph()
    n2 = StreamNormalizer(graph2)
    for event in (late, early):
        graph2.apply(n2.process(event, kind="event"))
    assert _final_states(graph2) == _final_states(graph)
    assert len(session_edges(graph2, "hasState")) == 3
    # replays change nothing
    assert n2.process(late, kind="event") == StreamDelta()
    assert n2.process(early, kind="event") == StreamDelta()


def test_topology_node_completed_uses_agent_input_when_present() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    graph.apply(
        StreamNormalizer(graph).process(
            _node_event("topology.node.completed", **{"agent.input": "hello", "agent.output": "bye"}),
            kind="event",
        )
    )
    states = sorted(n["content"] for (t, _), n in graph.nodes.items() if t == "State")
    assert states == ["bye", "hello"]


def test_llm_started_creates_chain_down_to_llm_call() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    event = {
        "Timestamp": "2026-10-15 14:50:48.493184000",
        "SpanId": "0fafd3f43fd76292",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": "llm.started",
            "event.time": "2026-10-15T14:50:48.493184+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "agent.name": "moderator",
            "ioa_observe.agent.span_id": "427bddeaf7b098f0",
            "llm.call.id": "0fafd3f43fd76292",
            "llm.name": "azure/gpt-4o",
            "llm.input": "hi",
        },
    }
    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    graph.apply(normalizer.process(event, kind="event"))

    assert sorted(t for t, _ in graph.nodes) == [
        "Agent", "AgentCall", "LLM", "LLMCall", "MAS", "MASCall", "Session", "State",
    ]
    assert graph.nodes[("LLM", "llm-azure-gpt-4o")]["provider"] == "azure"
    agent_call = next(n for (t, _), n in graph.nodes.items() if t == "AgentCall")
    assert agent_call["spanId"] == "427bddeaf7b098f0"
    edge_types = {e["edge_type"] for e in graph.edges.values()}
    assert {"usesLLM", "executesLLM", "hasLLMCall", "hasAgentCall", "hasInitialState"} <= edge_types
    assert normalizer.process(event, kind="event") == StreamDelta()


def _llm_event(name: str, **extra: str) -> dict:
    started = name.endswith("started")
    return {
        "SpanId": "0fafd3f43fd76292",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": name,
            "event.time": "2026-10-15T14:50:48.493184+00:00" if started else "2026-10-15T14:50:48.496038+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "agent.name": "moderator",
            "ioa_observe.agent.span_id": "427bddeaf7b098f0",
            "llm.call.id": "0fafd3f43fd76292",
            "llm.name": "azure/gpt-4o",
            "llm.input": "hi",
            **extra,
        },
    }


def test_llm_started_then_completed_builds_states_and_transition() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    completed = _llm_event("llm.completed", **{"llm.output": "yo"})
    for event in (_llm_event("llm.started"), completed):
        graph.apply(normalizer.process(event, kind="event"))

    assert sorted(t for t, _ in graph.nodes) == [
        "Agent", "AgentCall", "LLM", "LLMCall", "MAS", "MASCall", "Session", "State", "State", "Transition",
    ]
    assert sorted(n["content"] for (t, _), n in graph.nodes.items() if t == "State") == ["hi", "yo"]
    call = next(n for (t, _), n in graph.nodes.items() if t == "LLMCall")
    assert call["endTime"] > call["startTime"]
    edge_types = {e["edge_type"] for e in graph.edges.values()}
    assert {"hasFinalState", "inputTo", "leadsTo", "correspondsToTransition"} <= edge_types
    assert normalizer.process(completed, kind="event") == StreamDelta()


def test_llm_completed_alone_creates_everything() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    graph.apply(
        StreamNormalizer(graph).process(_llm_event("llm.completed", **{"llm.output": "yo"}), kind="event")
    )
    assert {"LLM", "LLMCall", "AgentCall", "Transition"} <= {t for t, _ in graph.nodes}


def _tool_event(name: str, **extra: str) -> dict:
    return {
        "SpanId": "abb8ef27ca74034a",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": name,
            "event.time": "2026-10-15T14:50:49.664363+00:00" if name.endswith("started") else "2026-10-15T14:50:49.666468+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "ioa_observe.agent.span_id": "5371d7b3072ac5c7",
            "tool.name": "read_document",
            "tool.input": "in",
            **extra,
        },
    }


def _edges(graph) -> set[tuple[str, str, str]]:
    return {(e["edge_type"], e["from_id"], e["to_id"]) for e in graph.edges.values()}


def test_tool_events_link_to_existing_agent_call() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    node_started = _node_event("topology.node.started", **{"agent.name": "schedule_agent", "agent.input": "q"})
    node_started["SpanId"] = "5371d7b3072ac5c7"
    completed = _tool_event("tool.completed", **{"tool.output": "out", "tool.status": "success"})
    for event in (node_started, _tool_event("tool.started"), completed):
        graph.apply(normalizer.process(event, kind="event"))

    assert {"Tool", "ToolCall", "AgentCall", "Agent"} <= {t for t, _ in graph.nodes}
    edges = _edges(graph)
    assert ("usesTool", "5371d7b3072ac5c7", "read_document") in edges
    assert any(e[0] == "hasToolCall" for e in edges) and any(e[0] == "executesTool" for e in edges)
    call = next(n for (t, _), n in graph.nodes.items() if t == "ToolCall")
    assert call["success"] is True and call["endTime"] > call["startTime"]
    assert sorted(n["content"] for (t, _), n in graph.nodes.items() if t == "State" and n["content"] in ("in", "out")) == ["in", "out"]
    assert normalizer.process(completed, kind="event") == StreamDelta()


def test_a2a_tool_started_is_a_handoff_not_a_tool() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    a2a = {"tool.type": "a2a", "tool.name": "handoff_agent", "tool.input": "q"}
    started = _tool_event("tool.started", **a2a)
    graph.apply(normalizer.process(started, kind="event"))

    # no Tool/ToolCall; the target is an unattached Agent named tool.name
    assert list(graph.nodes) == [("Agent", "handoff_agent")]
    assert not graph.edges
    assert normalizer.process(started, kind="event") == StreamDelta()

    # an Agent of that name already there is used, not duplicated
    graph.apply(normalizer.process(_tool_event("tool.completed", **a2a, **{"tool.output": "out"}), kind="event"))
    assert list(graph.nodes) == [("Agent", "handoff_agent")]

    # the target's own events then replace the unattached node and connect it
    node = _node_event("topology.node.started", **{"agent.name": "handoff_agent", "agent.input": "q"})
    graph.apply(normalizer.process(node, kind="event"))
    assert [i for t, i in graph.nodes if t == "Agent"] == [node["SpanId"]]


def test_non_a2a_tool_started_adds_tool_and_tool_call_to_the_agent() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    node = _node_event("topology.node.started", **{"agent.name": "schedule_agent", "agent.input": "q"})
    node["SpanId"] = "5371d7b3072ac5c7"
    for event in (node, _tool_event("tool.started", **{"tool.type": "function"})):
        graph.apply(normalizer.process(event, kind="event"))
    assert {"Tool", "ToolCall"} <= {t for t, _ in graph.nodes}
    edges = _edges(graph)
    assert ("usesTool", "5371d7b3072ac5c7", "read_document") in edges
    assert any(e[0] == "hasToolCall" for e in edges)


def _card_event(content: str) -> dict:
    return {
        "SpanId": "",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "event.name": "a2a.agent_card",
            "event.time": "2026-10-15T14:50:40.000000+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "capability.content": content,
        },
    }


def test_a2a_agent_card_creates_unattached_agent_then_events_connect_it() -> None:
    import json

    from norm import InMemoryGraph, StreamNormalizer

    span = "427bddeaf7b098f0"  # the node.started event's span: the agent's id
    card = json.dumps({"name": "schedule_agent", "description": "Finds schedules.", "skills": []})
    agents = lambda g: sorted(i for t, i in g.nodes if t == "Agent")
    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    graph.apply(normalizer.process(_card_event(card), kind="event"))
    assert sorted(graph.nodes) == [
        ("Agent", "schedule_agent"),
        ("MAS", "noa-trip-planner-mas"),
        ("Session", "213dad2f"),
    ]
    assert graph.nodes[("Agent", "schedule_agent")]["description"] == "Finds schedules."
    assert ("belongsToMAS", "schedule_agent", "noa-trip-planner-mas") in _edges(graph)
    assert ("executesSession", "213dad2f", "noa-trip-planner-mas") in _edges(graph)
    assert normalizer.process(_card_event(card), kind="event") == StreamDelta()

    # the agent's own event replaces the unattached node by one keyed on its span id,
    # keeping the description, and connects it
    node_started = _node_event("topology.node.started", **{"agent.name": "schedule_agent", "agent.input": "q"})
    graph.apply(normalizer.process(node_started, kind="event"))
    assert agents(graph) == [span]
    assert graph.nodes[("Agent", span)]["description"] == "Finds schedules."
    assert graph.nodes[("Agent", span)]["name"] == "schedule_agent"
    edges = _edges(graph)
    assert ("belongsToMAS", span, "noa-trip-planner-mas") in edges
    assert any(e[0] == "executesAgent" and e[2] == span for e in edges)
    assert not any("schedule_agent" in (e[1], e[2]) for e in edges)

    # a card arriving after the agent exists updates its description only: no second Agent
    late = InMemoryGraph()
    late_normalizer = StreamNormalizer(late)
    late.apply(late_normalizer.process(node_started, kind="event"))
    assert late.nodes[("Agent", span)]["description"] == ""
    edges_before = _edges(late)
    late.apply(late_normalizer.process(_card_event(card), kind="event"))
    assert agents(late) == [span]
    assert late.nodes[("Agent", span)]["description"] == "Finds schedules."
    newer = json.dumps({"name": "schedule_agent", "description": "Updated.", "version": "2"})
    late.apply(late_normalizer.process(_card_event(newer), kind="event"))
    assert late.nodes[("Agent", span)]["description"] == "Updated."
    assert _edges(late) == edges_before
    # a card without a description leaves the existing one alone
    nameless = json.dumps({"name": "schedule_agent"})
    assert late_normalizer.process(_card_event(nameless), kind="event") == StreamDelta()

    for bad in ("not json", "[]", "{}"):
        empty = InMemoryGraph()
        empty.apply(StreamNormalizer(empty).process(_card_event(bad), kind="event"))
        assert not empty.nodes


def test_llm_events_key_the_agent_on_its_span_id() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    graph.apply(normalizer.process(_llm_event("llm.started"), kind="event"))
    owning_span = "427bddeaf7b098f0"  # ioa_observe.agent.span_id of the llm events
    assert [i for t, i in graph.nodes if t == "Agent"] == [owning_span]
    assert any(e[0] == "usesLLM" and e[1] == owning_span for e in _edges(graph))


def test_tool_event_before_agent_is_linked_when_agent_arrives() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    graph.apply(normalizer.process(_tool_event("tool.started"), kind="event"))
    assert not {t for t, _ in graph.nodes} & {"Agent", "AgentCall"}
    assert not any(e[0] in ("hasToolCall", "usesTool") for e in _edges(graph))

    node_started = _node_event("topology.node.started", **{"agent.name": "schedule_agent", "agent.input": "q"})
    node_started["SpanId"] = "5371d7b3072ac5c7"
    graph.apply(normalizer.process(node_started, kind="event"))
    edges = _edges(graph)
    assert ("usesTool", "5371d7b3072ac5c7", "read_document") in edges
    assert any(e[0] == "hasToolCall" for e in edges)


def test_agent_card_without_session_is_skipped() -> None:
    import json

    from norm import InMemoryGraph, StreamNormalizer

    event = _card_event(json.dumps({"name": "schedule_agent", "description": "d"}))
    del event["LogAttributes"]["session.id"]
    graph = InMemoryGraph()
    graph.apply(StreamNormalizer(graph).process(event, kind="event"))
    assert not graph.nodes


def test_agent_card_agent_is_reused_not_duplicated_in_the_same_mas() -> None:
    import json

    from norm import InMemoryGraph, StreamNormalizer

    card = json.dumps({"name": "moderator", "description": "Routes."})
    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    graph.apply(normalizer.process(_card_event(card), kind="event"))
    graph.apply(normalizer.process(_node_event("topology.node.started", **{"agent.input": "q"}), kind="event"))
    assert [i for t, i in graph.nodes if t == "Agent"] == ["427bddeaf7b098f0"]
    assert graph.nodes[("Agent", "427bddeaf7b098f0")]["description"] == "Routes."
    assert ("belongsToMAS", "427bddeaf7b098f0", "noa-trip-planner-mas") in _edges(graph)


def test_agent_span_uses_the_unattached_agent_of_the_same_name() -> None:
    import json

    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    card = json.dumps({"name": "concierge", "description": "Plans trips."})
    card_event = _card_event(card)
    card_event["LogAttributes"]["session.id"] = "app_s1"  # the span's MAS
    graph.apply(normalizer.process(card_event, kind="event"))
    assert ("Agent", "concierge") in graph.nodes

    # the span has no agent_id: the agent is known by its name, same as the card's
    span = _agent_span()
    del span["SpanAttributes"]["agent_id"]
    span["SpanAttributes"]["ioa_observe.entity.name"] = "concierge"
    graph.apply(normalizer.process(span))
    assert [i for t, i in graph.nodes if t == "Agent"] == ["concierge"]
    assert graph.nodes[("Agent", "concierge")]["description"] == "Plans trips."
    edges = _edges(graph)
    assert ("belongsToMAS", "concierge", "app") in edges
    assert any(e[0] == "executesAgent" and e[2] == "concierge" for e in edges)


def test_agent_span_does_not_reuse_the_agent_of_another_mas() -> None:
    import json

    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    card_event = _card_event(json.dumps({"name": "concierge", "description": "Plans trips."}))
    graph.apply(normalizer.process(card_event, kind="event"))  # MAS noa-trip-planner-mas
    span = _agent_span()
    del span["SpanAttributes"]["agent_id"]
    span["SpanAttributes"]["ioa_observe.entity.name"] = "concierge"
    graph.apply(normalizer.process(span))  # MAS app
    assert sorted(i for t, i in graph.nodes if t == "Agent") == ["app:concierge", "concierge"]
    assert graph.nodes[("Agent", "app:concierge")]["description"] == ""


def _a2a_message_event(name: str, time: str) -> dict:
    return {
        "SpanId": "eac988190841ce1d",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": name,
            "event.time": time,
            "session.id": "noa-trip-planner-mas_213dad2f",
            "message.id": "m-1",
            "message.input": '{"messageId": "m-1"}',
            "source.agent": "moderator",
            "source.agent.span.id": "468f32a08faa2d00",
            "target.agent": "Schedule Agent",
            "span.id": "eac988190841ce1d",
        },
    }


def test_a2a_message_sent_builds_sender_chain_and_keeps_the_message() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    sent = _a2a_message_event("a2a.message.sent", "2026-10-15T14:50:47.000000+00:00")
    graph.apply(normalizer.process(sent, kind="event"))

    assert sorted(t for t, _ in graph.nodes) == [
        "Agent", "Agent", "AgentCall", "MAS", "MASCall", "Session", "State",
    ]
    assert {"468f32a08faa2d00", "Schedule Agent"} == {i for t, i in graph.nodes if t == "Agent"}
    call = next(i for t, i in graph.nodes if t == "AgentCall")
    state = next(i for t, i in graph.nodes if t == "State")
    edges = _edges(graph)
    assert ("hasState", call, state) in edges
    assert not any(e[0] in ("hasInitialState", "hasFinalState") for e in edges)
    assert not any("Schedule Agent" in (e[1], e[2]) for e in edges)  # recipient left unattached
    assert normalizer.process(sent, kind="event") == StreamDelta()


def test_a2a_message_received_keeps_the_message_on_the_recipients_call() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    received = _a2a_message_event("a2a.message.received", "2026-10-15T14:50:47.020000+00:00")

    # the recipient's call is not there yet: the same nodes as sent, but no State
    graph.apply(normalizer.process(received, kind="event"))
    assert "State" not in {t for t, _ in graph.nodes}
    assert "Schedule Agent" in {i for t, i in graph.nodes if t == "Agent"}

    # once the recipient's own node.started has created its call, the message is kept on it
    node = _node_event("topology.node.started", **{"agent.name": "Schedule Agent", "agent.input": "q"})
    node["SpanId"] = "4163c385d3710aac"
    graph.apply(normalizer.process(node, kind="event"))
    graph.apply(normalizer.process(received, kind="event"))
    receiver_call = next(
        n["id"] for (t, _), n in graph.nodes.items() if t == "AgentCall" and n["spanId"] == "4163c385d3710aac"
    )
    message_states = [
        e["to_id"] for e in graph.edges.values()
        if e["edge_type"] == "hasState" and e["from_id"] == receiver_call
        and graph.nodes[("State", e["to_id"])]["content"] == '{"messageId": "m-1"}'
    ]
    assert len(message_states) == 1
    assert normalizer.process(received, kind="event") == StreamDelta()


def _tools_discovered_event(with_span: bool = True, content: str | None = None) -> dict:
    import json

    attrs = {
        "event.name": "mcp.tools.discovered",
        "event.time": "2026-10-15T14:50:48.000000+00:00",
        "session.id": "noa-trip-planner-mas_213dad2f",
        "capability.content": content
        if content is not None
        else json.dumps(
            {
                "tools": [
                    {"name": "list_docs", "description": "List documents."},
                    {"name": "read_doc", "description": None},
                    {"description": "nameless, skipped"},
                ]
            }
        ),
    }
    if with_span:
        attrs["ioa_observe.agent.span_id"] = "4163c385d3710aac"
    return {"SpanId": "b0877c49a582c991", "ServiceName": "someone-else", "LogAttributes": attrs}


def test_mcp_tools_discovered_creates_mas_session_agent_and_tools() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    # no ioa_observe.agent.span_id: skipped
    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    assert normalizer.process(_tools_discovered_event(with_span=False), kind="event") == StreamDelta()

    event = _tools_discovered_event()
    graph.apply(normalizer.process(event, kind="event"))
    assert sorted(t for t, _ in graph.nodes) == ["Agent", "MAS", "Session", "Tool", "Tool"]
    # the MAS is named by the first part of session.id, not by application_id / ServiceName
    assert ("MAS", "noa-trip-planner-mas") in graph.nodes
    assert ("Session", "213dad2f") in graph.nodes
    assert ("Agent", "4163c385d3710aac") in graph.nodes
    assert graph.nodes[("Tool", "list_docs")]["description"] == "List documents."
    assert ("Tool", "read_doc") in graph.nodes
    edges = _edges(graph)
    assert ("belongsToMAS", "4163c385d3710aac", "noa-trip-planner-mas") in edges
    assert ("executesSession", "213dad2f", "noa-trip-planner-mas") in edges
    assert ("usesTool", "4163c385d3710aac", "list_docs") in edges
    assert ("usesTool", "4163c385d3710aac", "read_doc") in edges
    assert normalizer.process(event, kind="event") == StreamDelta()

    # bad content: the agent, session and MAS are still ensured, no tools
    bare = InMemoryGraph()
    bare.apply(StreamNormalizer(bare).process(_tools_discovered_event(content="not json"), kind="event"))
    assert sorted(t for t, _ in bare.nodes) == ["Agent", "MAS", "Session"]


def test_mcp_tools_discovered_reuses_existing_agent_and_tool() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    node = _node_event("topology.node.started", **{"agent.name": "schedule_agent", "agent.input": "q"})
    node["SpanId"] = "4163c385d3710aac"
    tool = _tool_event("tool.started", **{"tool.name": "list_docs"})
    tool["LogAttributes"]["ioa_observe.agent.span_id"] = "4163c385d3710aac"
    for event in (node, tool):
        graph.apply(normalizer.process(event, kind="event"))
    assert graph.nodes[("Tool", "list_docs")]["description"] == ""

    graph.apply(normalizer.process(_tools_discovered_event(), kind="event"))
    # the agent keeps its name, the tool gets its description, nothing is duplicated
    assert graph.nodes[("Agent", "4163c385d3710aac")]["name"] == "schedule_agent"
    assert sum(1 for t, _ in graph.nodes if t == "Agent") == 1
    assert graph.nodes[("Tool", "list_docs")]["description"] == "List documents."

    # a later event naming an agent created here fills in its name
    other = InMemoryGraph()
    other_normalizer = StreamNormalizer(other)
    other.apply(other_normalizer.process(_tools_discovered_event(), kind="event"))
    assert other.nodes[("Agent", "4163c385d3710aac")]["name"] == ""
    other.apply(other_normalizer.process(node, kind="event"))
    assert other.nodes[("Agent", "4163c385d3710aac")]["name"] == "schedule_agent"


def _mcp_message_sent_event(message_input: str) -> dict:
    return {
        "SpanId": "853e8b719de2f1ac",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": "mcp.message.sent",
            "event.time": "2026-10-15T14:50:48.000000+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "message.input": message_input,
            "source.agent": "Schedule Agent",
            "source.agent.span.id": "4163c385d3710aac",
            "span.id": "853e8b719de2f1ac",
            "target.agent": "debug",
        },
    }


def test_mcp_message_sent_creates_tool_and_tool_call_for_the_sender() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    # empty input, no tool name, or not JSON: ignored
    for ignored in ("", "{}", '{"arguments": {}}', "not json"):
        assert normalizer.process(_mcp_message_sent_event(ignored), kind="event") == StreamDelta()

    call_input = '{"arguments": {}, "name": "list_schedule_documents"}'
    sent = _mcp_message_sent_event(call_input)
    graph.apply(normalizer.process(sent, kind="event"))
    assert sorted(t for t, _ in graph.nodes) == [
        "Agent", "AgentCall", "MAS", "MASCall", "Session", "State", "Tool", "ToolCall",
    ]
    assert graph.nodes[("Agent", "4163c385d3710aac")]["name"] == "Schedule Agent"
    assert ("Tool", "list_schedule_documents") in graph.nodes
    edges = _edges(graph)
    assert ("usesTool", "4163c385d3710aac", "list_schedule_documents") in edges
    assert {"hasToolCall", "executesTool", "executesAgent", "hasAgentCall", "hasInitialState"} <= {e[0] for e in edges}
    assert next(n["content"] for (t, _), n in graph.nodes.items() if t == "State") == call_input
    assert next(n["spanId"] for (t, _), n in graph.nodes.items() if t == "ToolCall") == "853e8b719de2f1ac"
    assert normalizer.process(sent, kind="event") == StreamDelta()

    # the agent's own node.started finds the AgentCall made here: one call, one agent
    node = _node_event("topology.node.started", **{"agent.name": "Schedule Agent", "agent.input": "q"})
    node["SpanId"] = "4163c385d3710aac"
    graph.apply(normalizer.process(node, kind="event"))
    assert sum(1 for t, _ in graph.nodes if t == "AgentCall") == 1
    assert sum(1 for t, _ in graph.nodes if t == "Agent") == 1


def test_mcp_message_completed_closes_the_tool_call_with_its_output() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    call_input = '{"arguments": {}, "name": "list_schedule_documents"}'
    output = '{"content": [{"text": "Celestia.txt"}], "isError": false}'
    sent = _mcp_message_sent_event(call_input)
    completed = _mcp_message_sent_event(call_input)
    completed["LogAttributes"].update(
        {"event.name": "mcp.message.completed", "event.time": "2026-10-15T14:50:50.000000+00:00", "message.output": output}
    )

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    for event in (sent, completed):
        graph.apply(normalizer.process(event, kind="event"))
    assert sorted(t for t, _ in graph.nodes) == [
        "Agent", "AgentCall", "MAS", "MASCall", "Session", "State", "State", "Tool", "ToolCall", "Transition",
    ]
    call = next(n for (t, _), n in graph.nodes.items() if t == "ToolCall")
    assert call["success"] is True and call["endTime"] > call["startTime"]
    assert sorted(n["content"] for (t, _), n in graph.nodes.items() if t == "State") == sorted([call_input, output])
    assert {"hasFinalState", "inputTo", "leadsTo", "correspondsToTransition"} <= {e["edge_type"] for e in graph.edges.values()}
    assert normalizer.process(completed, kind="event") == StreamDelta()

    # completed alone builds everything sent does, plus the final State and Transition
    alone = InMemoryGraph()
    alone.apply(StreamNormalizer(alone).process(completed, kind="event"))
    assert sorted(t for t, _ in alone.nodes) == sorted(t for t, _ in graph.nodes)

    # an error result marks the call failed; tools/list (empty input) is ignored
    failed = _mcp_message_sent_event(call_input)
    failed["LogAttributes"].update({"event.name": "mcp.message.completed", "message.output": '{"isError": true}'})
    bad = InMemoryGraph()
    bad.apply(StreamNormalizer(bad).process(failed, kind="event"))
    assert next(n for (t, _), n in bad.nodes.items() if t == "ToolCall")["success"] is False
    listing = _mcp_message_sent_event("{}")
    listing["LogAttributes"]["event.name"] = "mcp.message.completed"
    assert StreamNormalizer(InMemoryGraph()).process(listing, kind="event") == StreamDelta()


def test_one_tool_call_per_message_id_across_tool_and_mcp_events() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    call_input = '{"arguments": {}, "name": "list_schedule_documents"}'
    message_id = "b74c5046d0194ed7b005eee95857a563"
    sent = _mcp_message_sent_event(call_input)
    done = _mcp_message_sent_event(call_input)
    sent["LogAttributes"]["message.id"] = done["LogAttributes"]["message.id"] = message_id
    done["LogAttributes"].update(
        {"event.name": "mcp.message.completed", "event.time": "2026-10-15T14:50:50+00:00", "message.output": '{"isError": false}'}
    )
    # the tool.* events of the same call: another span, the same tool.call.id
    tool_started = _tool_event(
        "tool.started", **{"tool.name": "list_schedule_documents", "tool.call.id": message_id, "tool.input": "{}"}
    )
    tool_started["LogAttributes"]["ioa_observe.agent.span_id"] = "4163c385d3710aac"
    tool_done = _tool_event(
        "tool.completed",
        **{"tool.name": "list_schedule_documents", "tool.call.id": message_id, "tool.output": "[files]", "tool.status": "success"},
    )
    tool_done["LogAttributes"]["ioa_observe.agent.span_id"] = "4163c385d3710aac"

    for order in ((tool_started, tool_done, sent, done), (sent, done, tool_started, tool_done), (done, tool_done)):
        graph = InMemoryGraph()
        normalizer = StreamNormalizer(graph)
        for event in order:
            graph.apply(normalizer.process(event, kind="event"))
        assert [i for (t, i) in graph.nodes if t == "ToolCall"] == [message_id]
        assert [i for (t, i) in graph.nodes if t == "Tool"] == ["list_schedule_documents"]
        # one initial and one final State: whichever event came first set them
        assert sum(1 for e in graph.edges.values() if e["edge_type"] == "hasInitialState" and e["from_id"] == message_id) == 1
        assert sum(1 for e in graph.edges.values() if e["edge_type"] == "hasFinalState" and e["from_id"] == message_id) == 1


def test_mcp_message_received_is_handled_like_sent() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    call_input = '{"arguments": {}, "name": "list_schedule_documents"}'
    sent = _mcp_message_sent_event(call_input)
    received = _mcp_message_sent_event(call_input)
    received["SpanId"] = received["LogAttributes"]["span.id"] = "787755dd67a73066"  # the server side's own span
    received["LogAttributes"]["event.name"] = "mcp.message.received"
    for event in (sent, received):
        event["LogAttributes"]["message.id"] = "b74c5046d0194ed7b005eee95857a563"
        del event["LogAttributes"]["application_id"]  # as on the real received events

    alone = InMemoryGraph()
    alone.apply(StreamNormalizer(alone).process(received, kind="event"))
    assert sorted(t for t, _ in alone.nodes) == [
        "Agent", "AgentCall", "MAS", "MASCall", "Session", "State", "Tool", "ToolCall",
    ]
    assert ("MAS", "noa-trip-planner-mas") in alone.nodes  # named by session.id's first part

    # sent and received of one message: a single ToolCall
    both = InMemoryGraph()
    normalizer = StreamNormalizer(both)
    for event in (sent, received):
        both.apply(normalizer.process(event, kind="event"))
    assert [i for t, i in both.nodes if t == "ToolCall"] == ["b74c5046d0194ed7b005eee95857a563"]
    assert sorted(t for t, _ in both.nodes) == sorted(t for t, _ in alone.nodes)
    assert normalizer.process(received, kind="event") == StreamDelta()

    # tools/list (empty input) is ignored
    listing = _mcp_message_sent_event("{}")
    listing["LogAttributes"]["event.name"] = "mcp.message.received"
    assert StreamNormalizer(InMemoryGraph()).process(listing, kind="event") == StreamDelta()


def _edge_updated_event(source_span: str, target: str) -> dict:
    return {
        "SpanId": "4163c385d3710aac",
        "ServiceName": "noa-trip-planner-mas",
        "LogAttributes": {
            "application_id": "noa-trip-planner-mas",
            "event.name": "topology.edge.updated",
            "event.time": "2026-10-15T14:50:49.000000+00:00",
            "session.id": "noa-trip-planner-mas_213dad2f",
            "source.agent": "planner",
            "source.agent.span.id": source_span,
            "target.agent": target,
        },
    }


def test_edge_updated_bridges_the_handoff_between_two_agent_calls() -> None:
    from norm import InMemoryGraph, StreamNormalizer

    graph = InMemoryGraph()
    normalizer = StreamNormalizer(graph)
    first = _node_event("topology.node.started", **{"agent.name": "planner", "agent.input": "q"})
    first["SpanId"] = "aaaa"
    first_done = _node_event(
        "topology.node.completed", **{"agent.name": "planner", "agent.input": "q", "agent.output": "plan"}
    )
    first_done["SpanId"] = "aaaa"
    second = _node_event("topology.node.started", **{"agent.name": "worker", "agent.input": "do the plan"})
    second["SpanId"] = "bbbb"
    second["LogAttributes"]["event.time"] = "2026-10-15T14:50:48.900000+00:00"
    for event in (first, first_done, second):
        graph.apply(normalizer.process(event, kind="event"))
    assert "ProcessingCall" not in {t for t, _ in graph.nodes}

    # the source is found by its span id, the target by its name only
    handoff = _edge_updated_event("aaaa", "worker")
    graph.apply(normalizer.process(handoff, kind="event"))
    assert "ProcessingCall" in {t for t, _ in graph.nodes}
    assert "Processing" in {t for t, _ in graph.nodes}
    assert any(e["edge_type"] == "hasProcessingCall" for e in graph.edges.values())
    assert normalizer.process(handoff, kind="event") == StreamDelta()

    # a target that is no agent with a call (an MCP server) matches nothing
    assert normalizer.process(_edge_updated_event("aaaa", "debug"), kind="event") == StreamDelta()
    # nor does an unknown source span
    assert normalizer.process(_edge_updated_event("nope", "worker"), kind="event") == StreamDelta()
