# wayfarer

A clickable web-UI prototype for driving agent work along the
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

## Prototype screens

| file | what it shows |
|---|---|
| `index.html` | the line — every station, and where work currently sits |
| `first-run.html` | connecting a repo for the first time |
| `wayfinder-map.html` | charting the way through a piece of work |
| `spec-reader.html` | reading the spec a run produced |
| `ticket-graph.html` | the slice into tickets and their dependencies |
| `live-build.html` | a build in progress |
| `review-desk.html` | reviewing what came back |

`docs/` carries the intent behind each screen: `CONTEXT.md` for the vocabulary,
`docs/design/` for the shell and visual language, `docs/screens/` per screen.

## Naming

The prototype's own docs call it **Waystation**, which collides with
[`jeffrichley/waystation`](https://github.com/jeffrichley/waystation) — a bare
Python library for orchestrating sandboxed AI coding agents. Those are two
different things and the names are not settled. Treat every name in here as
provisional.

## Provenance

Designed in Open Design. Exported 2026-09-20 from the project's live files;
editor scaffolding and intermediate version history are deliberately not
included.
