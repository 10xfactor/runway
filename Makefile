.PHONY: install check test ui e2e fixtures build
install:
	uv sync --all-extras && cd ui && pnpm install
check:
	.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy src && .venv/bin/lint-imports
test:
	.venv/bin/pytest -q && cd ui && pnpm tsc --noEmit && pnpm vitest run
ui:
	cd ui && pnpm build
e2e: ui
	cd ui && pnpm exec playwright test
fixtures:
	.venv/bin/python scripts/gen_fixtures.py
build: ui
	uv build
