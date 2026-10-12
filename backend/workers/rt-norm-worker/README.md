# rt-norm-worker

Standalone worker (no `worker-base`) that reads `~/claris/otel_traces.json` and prints the spans one by one.

```bash
cd backend
uv run --package rt-norm-worker rt-norm-worker-cli [--input PATH]
```
