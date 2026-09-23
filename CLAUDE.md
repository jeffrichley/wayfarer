# Wayfarer

A companion web app for the [mattpocock/skills](https://github.com/mattpocock/skills)
workflow. It follows work along the skill line on one GitHub repo and lets a
person steer the agents doing it.

**Wayfarer is the app. [Waystation](https://github.com/jeffrichley/waystation) is
the library it runs on** — a sister repo holding the Python primitives for
orchestrating sandboxed agent runs. The two names are not interchangeable. Parts
of `docs/` still call the app "Waystation"; that is stale and being renamed.

The app is `src/wayfarer` (one Python process) and `web/` (its React page). The
clickable HTML prototype it is built from sits beside them; see `README.md` for
the screens and `docs/README.md` for the intent.

## Working a ticket

**The ticket is the spec, and claiming it is your first write.** Run
`gh issue edit <n> --add-assignee @me` before the branch and before the first
edit. An assignee is how the next agent reading the frontier knows the ticket is
taken — and it is exactly what Wayfarer's own cascade reads as a claim — so an
unclaimed ticket becomes two agents' work.

**Done means CI green on the PR.** `just check` is the fast local signal and CI
runs the same recipes on Ubuntu and macOS, so a local pass is evidence and the
PR's run is the verdict. Push the branch, watch the run, and fix what it finds.
Hold the coverage floor where it is, and add a lint ignore only with the reason
written beside it.

**Green means land it.** When every job passes, the merge is yours to make:
`gh pr merge <n> --merge --delete-branch`, then `git fetch --prune`. A green PR
left sitting is the ticket unfinished.

## Rules that live nowhere else

- **Every shape the browser sees is a pydantic model in `src/wayfarer/models.py`**,
  and `web/src/api.gen.ts` is regenerated from it (`just types`) in the same
  commit (ADR-0004). CI fails on drift, and a test fails for a model the schema
  does not carry.
- **Every bound is a named setting.** Waystation defaults every timeout to
  unbounded, so Wayfarer is where the spec's caps are set; a number no ticket
  asked for is a setting or it is a comment saying why it must exist.
- **Cite the decision in the code.** A bare `(ADR-0004)` in a comment is how the
  next reader finds the argument.
- **Prefer a test to a paragraph.** When a ticket settles something structural,
  leave a test holding it.
- **Inject what varies, straight-line the rest.** A platform or backend `if`
  inside a method is a strategy wanting to be born; a strategy earns its place
  only when you can name its second implementation. When two shapes both look
  defensible, a named precedent (stdlib, uvicorn, a library with the same
  problem) wins over taste.

## Tests

Test at the HTTP surface, driving Wayfarer as a person and the browser do: the
`wayfarer` console script in a temp clone, then HTTP against it
(`tests/conftest.py` has the launcher). Name each test for the behaviour, as a
sentence about the app.

Mark each module by what it needs — `unit`, `git`, `docker`, `live` — so the
cheap tiers run anywhere; `live` spends real credentials and never runs by
default or in CI. Poll for the signal itself rather than sleeping a fixed time.
The 90% branch-coverage floor is a floor: cover behaviour, and leave a
genuinely unreachable branch uncovered rather than contorting a test to reach it.

## Commits

**Secrets stay out of every commit.** Credentials live in the environment
Wayfarer is launched from, or a gitignored `.env`. Run `just hooks` once per
clone: gitleaks then scans every commit and push (`.gitleaks.toml`), and CI
scans again. When the scan finds something, rotate the secret and rewrite the
commit.

Conventional commits (`feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
`chore:`), one concern each. A commit an agent wrote carries a
`Co-Authored-By` trailer naming it. Work on a branch; `main` lands through PRs.

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage labels, unchanged. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at the root, ADRs in `docs/adr/`. See `docs/agents/domain.md`.

### Docs

`docs/` is an OKF bundle managed by vaultwright. Read `docs/CLAUDE.md` before creating or changing anything under `docs/`.
