# wayfarer

A clickable web-UI prototype for driving agent work along the
[mattpocock/skills](https://github.com/mattpocock/skills) line:
`/wayfinder` → `/to-spec` → `/to-tickets` → `/tdd` → `/code-review` → merge.

**This repository is the prototype, not the codebase.** The screens are static
HTML with no backend. They exist to settle what the thing should look like and
how it should behave before any of it is built.

## Screens

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
