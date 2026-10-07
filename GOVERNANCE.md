# Governance

Runway is a 10x Factor Community Initiative, MIT licensed.

- **Contributors**: anyone with a merged PR. Commits need a DCO sign-off (`git commit -s`); there is no CLA.
- **Maintainers**: contributors with sustained, reviewed work, nominated by a maintainer and approved by lazy consensus
  over 7 days. Maintainers review and merge; two approvals for anything touching the event schema or public API.
- **Changes to the event schema, public API (`runway.extensions`, `runway.api`), or plugin contracts** need an RFC in
  `docs/rfcs/`. The stable surface follows semver after 1.0.
- **Disputes**: discuss on the issue; if unresolved, maintainers vote by simple majority.
