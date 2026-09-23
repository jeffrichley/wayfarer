# Recipes mirrored by CI. Local green ⇒ CI green.

set shell := ["bash", "-cu"]

export COREPACK_ENABLE_DOWNLOAD_PROMPT := "0"

pnpm := "corepack pnpm --dir web"

default:
    @just --list

# Lint, type-check and test both halves. Fails if any step fails.
check: web-check python-check

# The page: install, lint, type-check, build into the package.
web-check:
    {{pnpm}} install --frozen-lockfile
    {{pnpm}} lint
    {{pnpm}} typecheck
    {{pnpm}} build

# The process: lint, type-check, test. The tests serve the built page, so build it first.
python-check:
    uv run ruff check src tests hatch_build.py
    uv run ruff format --check src tests hatch_build.py
    uv run mypy
    uv run pytest

# Install the Chromium the browser tier drives (tests marked `browser`), once per machine.
browser:
    uv run playwright install --with-deps chromium

# Regenerate the browser's types from the Python models (web/src/api.gen.ts).
types:
    {{pnpm}} gen:types

# Fail if web/src/api.gen.ts no longer matches the Python models.
types-drift: types
    git diff --exit-code -- web/src/api.gen.ts

# Install the secret-scanning hooks (.pre-commit-config.yaml), once per clone.
hooks:
    uv run pre-commit install

# Build the sdist and wheel; the wheel carries the page.
build:
    uv build
