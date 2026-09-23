# wayfarer

A web UI for driving agent work along the
[mattpocock/skills](https://github.com/mattpocock/skills) line:
`/wayfinder` → `/to-spec` → `/to-tickets` → `/tdd` → `/code-review` → merge.

The repository holds two things: the **app** being built (`src/wayfarer`, the
Python process, and `web/`, its React page), and the **prototype** it is built
from — static HTML screens with no backend, which settled what the thing should
look like and how it should behave.

## Running it

Inside a clone of the repo Wayfarer should work on:

```bash
wayfarer
```

It serves on `127.0.0.1` (port 7431, or a free one if that is taken) and opens
your browser. One instance per clone: a second refuses, naming the first.
Ctrl-C stops it.

## Developing

Needs [uv](https://docs.astral.sh/uv/), Node 24 (pnpm comes through corepack),
and [just](https://just.systems/).

| command | what it does |
|---|---|
| `just check` | lint, type-check and build the page, then lint, type-check and test the process — what CI runs |
| `just types` | regenerate `web/src/api.gen.ts` from the Python models; CI fails if it drifts |
| `just build` | build the sdist and wheel; the wheel carries the built page, so users need no Node |
| `corepack pnpm --dir web dev` | the Vite dev server, proxying `/api` to a running `wayfarer` |

Every shape the browser sees is a pydantic model in `src/wayfarer/models.py`.
Change one, run `just types`, and commit both.

## The prototype is a frozen reference, not the app

`prototype/` holds seven static HTML screens with no backend. They settled what
Wayfarer should look like and how it should behave before any of it was built,
and they are now the fixed answer to "does it look right?".

Frozen means:

- **Don't edit it** to match the app. When the two disagree, the prototype is the
  reference for the look, and the spec is the reference for behaviour.
- **It keeps no demo state.** Every screen opens at the same moment every time,
  and nothing a click does carries to another screen or survives a reload.
- **Pieces are named by `data-piece`.** The real UI uses the same names, so a
  piece in the app can be found in the prototype by searching for it.

Open any file in a browser; there is nothing to build or serve.

| file | what it shows |
|---|---|
| `prototype/index.html` | the line — every station, and where work currently sits |
| `prototype/first-run.html` | connecting a repo for the first time |
| `prototype/wayfinder-map.html` | charting the way through a piece of work |
| `prototype/spec-reader.html` | reading the spec a run produced |
| `prototype/ticket-graph.html` | the slice into tickets and their dependencies |
| `prototype/live-build.html` | a build in progress |
| `prototype/review-desk.html` | reviewing what came back |

`CONTEXT.md` at the root carries the vocabulary. `docs/` carries the intent behind
each screen: `docs/design/` for the shell and visual language, `docs/screens/` per
screen. Several screen writeups still describe behaviour that later decisions
ruled out; [#27](https://github.com/jeffrichley/wayfarer/issues/27) lists which.

## Naming

**Wayfarer is this app. [Waystation](https://github.com/jeffrichley/waystation) is
the library it runs on** — a sister repo of Python primitives for orchestrating
sandboxed AI coding agents. Settled 2026-09-20.

Parts of `docs/` and the prototype's visible copy (its wordmark and page titles)
still call this app "Waystation". That naming is stale; read it as Wayfarer.

## Provenance

Designed in Open Design. Exported 2026-09-20 from the project's live files;
editor scaffolding and intermediate version history are deliberately not
included.
