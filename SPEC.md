# Runway Spec (v0.1, draft)

Normative invariants. The authoritative event shapes come from `runway events-schema`.

1. **Agents propose, the runtime commits.** An artifact becomes visible to downstream tasks only after every validator
   stage accepts it. Nothing else writes to the workspace.
2. **Events are the source of truth.** State changes are appended to `events`; `runs.snapshot_json` is a projection
   produced by the pure reducer `apply_event`, written in the same transaction.
3. **Events carry no payloads.** Artifacts are content-addressed (`id = fingerprint({schema, payload})`); events hold
   ids, hashes, counts, issue codes, and redacted free text.
4. **Validation is structured.** A `ValidationResult` is ACCEPTED, REJECTED (with issues: code, path, message, hint) or
   ERROR. Validator crashes are ERROR and never trigger an LLM retry. Unparseable model output counts as an attempt.
5. **Repair is bounded.** Retries are limited by task and run budgets (tokens, cost, time, retries). Identical repeated
   output stops the loop. Failed tasks fail fast and skip their dependents.
6. **Cache keys** combine task@version, agent config hash, input/output schema hashes, validator fingerprint, and
   input artifact refs. Replay is a child run that reuses verified upstream outputs (`task.cached`).
7. **Ports and adapters.** `core` is pure; `ports` are protocols; `adapters` do I/O; `runtime` composes. Enforced by
   import-linter.
8. **Extensions** register via entry points (`runway ext list`). The stable surface is `runway.extensions` and
   `runway.api`.
