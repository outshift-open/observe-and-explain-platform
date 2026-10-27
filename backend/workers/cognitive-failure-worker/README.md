# cognitive-failure-worker

Detects the cognitive failures of the challenges taxonomy in a session and writes a `CognitiveFailureReport`
for each: the failure code, a `low`/`medium`/`high` confidence and a brief reasoning, attached to the session
and to the call where it happened.

It fetches the session's trajectory from the knowledge graph, writes it to a temporary file (deleted
afterwards) and lets an agent read it with `list_steps`, `read_step` and `grep` tools, with no access to the API
or the graph, to find the configured failures. It reports through a schema-enforced `submit_detections` tool,
and the worker writes a report per detection.

Which failures to look for is set in `cognitive_failure_config.yaml` (see
[`backend/cognitive_failure_config.yaml`](../../cognitive_failure_config.yaml)); with none, nothing is
detected. The full description, the graph model and the settings are in the
[worker documentation](../../docs/workers/cognitive-failure-worker.md).

```bash
cognitive-failure-worker-cli --config-file cognitive_failure_config.yaml
```

`data/failures.json` comes from the taxonomy: `python scripts/build_failures.py path/to/challenges-taxonomy.md`.
