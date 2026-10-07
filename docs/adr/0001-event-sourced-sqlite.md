# ADR 0001: Event-sourced SQLite as the single source of truth

Status: accepted

## Context
Runs must be replayable, auditable, and inspectable from CLI and UI without drift between them.

## Decision
All state changes are appended to an `events` table. `runs.snapshot_json` is a projection maintained in the same
transaction by the pure reducer `apply_event`. The UI folds the same events with a mirrored reducer; both are verified
against golden fixtures in `fixtures/scenarios/`. Events never contain payloads; artifacts are content-addressed files.

## Consequences
- Replay creates a child run reusing verified upstream artifacts (`task.cached`).
- Event schema changes need an RFC and a fixture update.
- Payloads stay out of the log, so the log is safe to share.
