# cognition-protocols-worker

One OXP worker for Cognition protocols. For each session it:

1. **detects** which Cognition protocols the session's agents had (*enabled*) and used (*activated*), from the
   session's spans in the KG;
2. **records** that: an `CognitionProtocolReport` lists the protocols enabled and those activated, and each *activated* protocol gets
   an `CognitionProtocolExecutionReport` with the agents and skills that had it and used it (a protocol that was only
   enabled gets none);
3. **evaluates** every protocol found *activated* that has an evaluator, and attaches the metrics to that
   protocol's execution report as `MetricResult` nodes.

ACCORD and CONCORD are built in:

| Protocol | Detector (skills) | Evaluator (MCE metrics) |
|---|---|---|
| `accord` | `l9-accord-*` | `ioc-accord-mce-metrics`, `protocols/accord_mce_config.yaml` |
| `concord` | `l9-concord-*` (`initiator`, `receiver`) | `ioc-concord-mce-metrics`, `protocols/concord_mce_config.yaml` |

CONCORD is *enabled* when an agent's prompt lists a `l9-concord-*` skill and *activated* when one is called
(`activate_skill`, or `run_skill_script` against it). Its metrics read the initiator script's own calls, so a
session where only a specialist activated the receiver is recorded as activated and every metric is skipped.
All graph access goes through the platform's providers (`OXPKGProvider` to read, `OXPCognitionProtocolReportProvider` to
write); the worker holds no queries.

```bash
cognition-protocols-worker-cli                                  # consume new_session_to_cognition_protocols
cognition-protocols-worker-cli --run-once --input msg.json --output out.json   # one session: {"session_id": "..."}
```

Settings: `RABBITMQ_*`, `NEO4J_URI` / `NEO4J_AUTH` (or `NEO4J_USERNAME` / `NEO4J_PASSWORD`), `COGNITION_PROTOCOLS_INPUT_QUEUE`,
`COGNITION_PROTOCOLS_OUTPUT_QUEUE`, `COGNITION_PROTOCOLS_FEEDBACK_QUEUE`; `LLM_API_KEY`, `LLM_MODEL_NAME`, `LLM_BASE_MODEL_URL`
for LLM-judged metrics.

## Adding a protocol

A protocol is a **detector** (is it present, is it used?) and, if it has metrics, an **evaluator** with the
same `name`. Both are plugins: register them in code, or from another package as entry points, with nothing
changed here.

### Detector

A protocol whose agents get it as skills with a common name prefix needs no code:

```python
from cognition_protocols_worker.detectors import SkillProtocolDetector

SkillProtocolDetector("concord", "l9-concord-")
```

Any other protocol subclasses `ProtocolDetector`:

```python
from cognition_protocols_worker.detectors import ProtocolDetector, ProtocolFinding, SessionSpans

class ConcordDetector(ProtocolDetector):
    name = "concord"

    def detect(self, context):
        spans = SessionSpans.of(context)          # .agents, .llms, .tools, .agent_of(span)
        found = ProtocolFinding(self.name)
        ...                                       # fill enabled / activated and the *_by_agent maps
        return found
```

```toml
[project.entry-points.cognition_protocol_detectors]
concord = "my_package.detectors:ConcordDetector"
```

### Evaluator

If the protocol's metrics are MCE plugins (a package registering them under
`metrics_computation_engine.plugins`), list them in an MCE worker config and use `McEvaluator`:

```python
from cognition_protocols_worker.evaluators import McEvaluator

def evaluator():
    return McEvaluator("concord", "/path/to/concord_mce_config.yaml")
```

```toml
[project.entry-points.cognition_protocol_evaluators]
concord = "my_package.evaluator:evaluator"
```

The config is MCE's worker-config format (see `protocols/accord_mce_config.yaml`: the metrics under
`metrics: Session:` and `cache: {read: false, write: false}` so nothing is stored on the Session). For
anything else, subclass `ProtocolEvaluator` and return an `Evaluation(passed=[...MetricResult], failed=[...])`.

An entry point may name a class, an instance, or a function returning one. A detector or evaluator that raises
is logged and skipped (the other protocols are still handled; the message is reported as failed so it can be
retried). Two plugins for the same protocol name are rejected, and a clashing entry point is not loaded.
