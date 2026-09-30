Policy files used by `stateful_evals_be`.

Built-in policies currently provided:
- `tau2_airline.md`
- `tau2_retail.md`
- `tau2_telecom.md`
- `noa.md`

Entry points:
- Runner (`run_reward_alignment.py`)
  - `--task-policy-map` for per-task policies
  - `--policy-file` for a single fallback policy
- Library (`stateful_evals_be.evaluate_spans`)
  - `policy_override` for the supplied session
- Compatibility batch API (`TemporalMetricsProcessor.run_evaluation`)
  - `policy_overrides` for per-session overrides

Future domains:
- Unknown domains do not have automatic defaults.
- Provide policy explicitly via runner/library entry points.
