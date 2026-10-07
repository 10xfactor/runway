# Contributing

```bash
make install        # uv sync + pnpm install
make check test     # ruff, mypy strict, import-linter, pytest, tsc, vitest
make e2e            # builds the UI and runs Playwright against a throwaway Console
```

Rules of the road:
- Sign off commits (`git commit -s`); use conventional commits (`feat:`, `fix:`, `docs:` ...).
- Layering is enforced: `core` has no I/O; adapters implement ports; `runtime` composes them. `lint-imports` must pass.
- The Python reducer (`core/snapshot.py`) and the TS reducer (`ui/src/lib/reducer.ts`) must stay in step. Regenerate
  fixtures with `make fixtures` and keep both golden tests green.
- Never put payloads, PHI, or PII in events, logs, or fixtures.
- Build on Runway without forking: write a plugin (entry-point groups listed by `runway ext list`).
