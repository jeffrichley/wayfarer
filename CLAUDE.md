# Wayfarer

A companion web app for the [mattpocock/skills](https://github.com/mattpocock/skills)
workflow. It follows work along the skill line on one GitHub repo and lets a
person steer the agents doing it.

**Wayfarer is the app. [Waystation](https://github.com/jeffrichley/waystation) is
the library it runs on** — a sister repo holding the Python primitives for
orchestrating sandboxed agent runs. The two names are not interchangeable. Parts
of `docs/` still call the app "Waystation"; that is stale and being renamed.

This repo currently holds a clickable HTML prototype and the design docs behind
it. See `README.md` for the screens and `docs/README.md` for the intent.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels, unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.

### Docs

`docs/` is an OKF bundle managed by vaultwright. Read `docs/CLAUDE.md` before creating or changing anything under `docs/`.
