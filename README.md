# wayfarer

A clickable web-UI prototype for driving agent work along the
[mattpocock/skills](https://github.com/mattpocock/skills) line:
`/wayfinder` â `/to-spec` â `/to-tickets` â `/tdd` â `/code-review` â merge.

**This repository is the prototype, not the codebase.** The screens are static
HTML with no backend. They exist to settle what the thing should look like and
how it should behave before any of it is built.

## Screens

| file | what it shows |
|---|---|
| `index.html` | the line â every station, and where work currently sits |
| `first-run.html` | connecting a repo for the first time |
| `wayfinder-map.html` | charting the way through a piece of work |
| `spec-reader.html` | reading the spec a run produced |
| `ticket-graph.html` | the slice into tickets and their dependencies |
| `live-build.html` | a build in progress |
| `review-desk.html` | reviewing what came back |

`CONTEXT.md` at the root carries the vocabulary. `docs/` carries the intent behind
each screen: `docs/design/` for the shell and visual language, `docs/screens/` per
screen.

## Naming

**Wayfarer is this app. [Waystation](https://github.com/jeffrichley/waystation) is
the library it runs on** — a sister repo of Python primitives for orchestrating
sandboxed AI coding agents. Settled 2026-09-20.

Parts of `docs/` still call this app "Waystation", as do the `assets/waystation.*`
filenames and the `data-od-id` values. That naming is stale; read it as Wayfarer.

## Provenance

Designed in Open Design. Exported 2026-09-20 from the project's live files;
editor scaffolding and intermediate version history are deliberately not
included.
