from types import SimpleNamespace

import pytest

from stateful_eval_worker.worker import StatefulEvalWorker

NEO4J_ENV = (
    "NEO4J_HOST",
    "NEO4J_PORT",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "NEO4J_DATABASE",
    "NEO4J_AUTH",
)


class _Driver:
    def __init__(self, uri):
        self.uri = uri
        self.close_calls = 0

    def verify_connectivity(self):
        pass

    def close(self):
        self.close_calls += 1


@pytest.fixture
def drivers(monkeypatch):
    import oxp.connectors.neo4j as neo4j_module
    import oxp.dependencies as dependencies

    opened = []

    def driver(uri, auth=None):
        opened.append(_Driver(uri))
        return opened[-1]

    monkeypatch.setattr(neo4j_module, "GraphDatabase", SimpleNamespace(driver=driver))
    monkeypatch.setattr(dependencies, "_neo4j_connector", None)
    for name in NEO4J_ENV:
        monkeypatch.delenv(name, raising=False)
    return opened


@pytest.mark.parametrize(
    "env",
    [
        {"NEO4J_HOST": "neo4j:7687", "NEO4J_URI": "bolt://neo4j:7687"},
        {"NEO4J_HOST": "neo4j", "NEO4J_PORT": "7687", "NEO4J_URI": "bolt://neo4j:7687"},
        {"NEO4J_HOST": "neo4j:7687"},
    ],
)
def test_metric_writes_share_the_base_worker_neo4j_driver(monkeypatch, rabbit_url, drivers, env):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    worker = StatefulEvalWorker(rabbit_url=rabbit_url, input_queue="test")
    worker.push_metrics = True
    worker._get_oxp_client()
    assert [d.uri for d in drivers] == ["bolt://neo4j:7687"]
    worker._close_db_handler()
    assert drivers[0].close_calls == 1
