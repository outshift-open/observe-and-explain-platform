#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0

import json
import threading
import urllib.error
import urllib.request

import pytest

from rt_norm_worker.rules import DEFAULT_RULES_PATH, Rule, RuleSet, load_rules, rule_from_dict
from rt_norm_worker.server import make_server


def test_default_rules_file_is_loaded_in_order() -> None:
    rules = load_rules(DEFAULT_RULES_PATH)
    assert rules.keys() == [
        "all", "tool_events", "tool_completed", "llm_events", "llm_completed",
        "mcp_traffic", "agent_handoffs", "service_events=weather-agent", "agent_events=researcher",
    ]
    assert rules.get("agent_events=researcher").value == "researcher"
    assert rules.get("all").callback_url == "http://localhost:8080/callbacks/all"


def test_a_rule_with_a_value_can_be_added_once_per_value() -> None:
    rules = RuleSet()
    assert rules.add(Rule("agent_events", "http://a", "researcher"))
    assert rules.add(Rule("agent_events", "http://b", "planner"))
    assert not rules.add(Rule("agent_events", "http://c", "planner"))  # replaces the callback
    assert rules.get("agent_events=planner").callback_url == "http://c"
    assert len(rules) == 2
    assert rules.remove("agent_events=researcher") and not rules.remove("agent_events=researcher")


@pytest.mark.parametrize(
    "item",
    [
        {"name": "nope", "callback_url": "u"},
        {"name": "all"},
        {"name": "agent_events", "callback_url": "u"},  # needs a value
        {"name": "all", "callback_url": "u", "value": "x"},  # takes none
        "all",
    ],
)
def test_invalid_rules_are_rejected(item) -> None:
    with pytest.raises(ValueError):
        rule_from_dict(item)


def test_duplicate_rules_in_a_file_are_rejected(tmp_path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text("rules:\n  - {name: all, callback_url: u}\n  - {name: all, callback_url: v}\n")
    with pytest.raises(ValueError):
        load_rules(path)


def _call(port: int, method: str, path: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def test_rules_are_managed_over_http() -> None:
    from norm import InMemoryGraph

    rules = RuleSet([Rule("all", "http://x")])
    server = make_server(InMemoryGraph(), "127.0.0.1", 0, rules)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        assert _call(port, "POST", "/rules", {"name": "agent_events", "value": "researcher", "callback_url": "http://r"})[0] == 201
        assert "agent_events=researcher" in rules
        assert _call(port, "POST", "/rules", {"rules": [{"name": "llm_events", "callback_url": "http://l"}]})[0] == 201
        assert _call(port, "POST", "/rules", {"name": "bogus", "callback_url": "u"})[0] == 400
        status, body = _call(port, "GET", "/rules")
        assert status == 200 and [r["key"] for r in body["rules"]] == ["all", "agent_events=researcher", "llm_events"]
        assert _call(port, "DELETE", "/rules/agent_events%3Dresearcher")[0] == 200
        assert _call(port, "DELETE", "/rules/agent_events%3Dresearcher")[0] == 404
        assert rules.keys() == ["all", "llm_events"]
    finally:
        server.shutdown()
        server.server_close()


def _log(name: str, service: str = "svc", **attrs: str) -> dict:
    return {"ServiceName": service, "LogAttributes": {"event.name": name, **attrs}}


def test_rules_match_the_log_attributes() -> None:
    def keys(rules: list[Rule], record: dict) -> list[str]:
        return [r.key for r in rules if r.matches(record)]

    every = [Rule(n, "u") for n, (_, takes) in __import__("rt_norm_worker.rules").rules.RULE_TYPES.items() if not takes]
    rules = every + [Rule("agent_events", "u", "researcher"), Rule("service_events", "u", "weather")]

    assert keys(rules, _log("tool.completed")) == ["all", "tool_events", "tool_completed"]
    assert keys(rules, _log("llm.started")) == ["all", "llm_events"]
    assert keys(rules, _log("mcp.message.sent", **{"network.protocol.name": "mcp"})) == ["all", "mcp_traffic"]
    handoff = _log("topology.edge.updated", **{"topology.edge.kind": "agent_handoff", "source.agent": "a", "target.agent": "b"})
    assert "agent_handoffs" in keys(rules, handoff)
    loop = _log("topology.edge.updated", **{"topology.edge.kind": "agent_handoff", "source.agent": "a", "target.agent": "a"})
    assert "agent_handoffs" not in keys(rules, loop)
    assert "agent_events=researcher" in keys(rules, _log("llm.started", **{"agent.name": "researcher"}))
    assert "agent_events=researcher" in keys(rules, _log("a2a.message.sent", **{"source.agent": "researcher"}))
    assert "agent_events=researcher" not in keys(rules, _log("llm.started", **{"agent.name": "other"}))
    assert "service_events=weather" in keys(rules, _log("llm.started", service="weather"))
    as_json = {"ServiceName": "svc", "LogAttributes": json.dumps({"event.name": "tool.started"})}
    assert "tool_events" in keys(rules, as_json)


def test_matching_logs_are_posted_to_the_callback_after_normalization() -> None:
    from norm import InMemoryGraph

    from rt_norm_worker.callbacks import Notifier
    from rt_norm_worker.worker import process_record

    calls: list[tuple[str, dict]] = []
    rules = RuleSet([Rule("tool_completed", "http://tool"), Rule("llm_events", "http://llm"), Rule("all", "http://boom")])

    def post(url: str, payload: dict) -> None:
        calls.append((url, payload))
        if url == "http://boom":
            raise OSError("down")  # a failing callback must not break anything

    notifier = Notifier(rules, post=post, wait=True)
    record = _log("tool.completed", **{"session.id": "m_s1", "tool.name": "t"})
    graph = InMemoryGraph()
    process_record(graph, record, "event", notifier)
    assert ("Tool", "t") in graph.nodes  # normalized first
    assert [u for u, _ in calls] == ["http://tool", "http://boom"]
    assert calls[0][1] == {"rule": "tool_completed", "value": "", "event": record}

    calls.clear()
    process_record(graph, {"SpanName": "x"}, "span", notifier)  # spans never call back
    assert calls == []
