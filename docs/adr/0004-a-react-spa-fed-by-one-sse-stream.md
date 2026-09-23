---
type: adr
title: Wayfarer's UI is a React SPA fed by one SSE stream
status: stable
---

# Wayfarer's UI is a React SPA fed by one SSE stream

The browser runs a single-page app in **React and TypeScript**, built with Vite. The Python process from ADR-0001 serves the built bundle and a JSON API with FastAPI. **SSE is the only way data reaches the browser.** Each page opens one stream, which sends a snapshot when it connects or reconnects, then upserts and removals keyed by id into one normalised client store (Zustand). Commands are `POST`s that return `202`, and their effect comes back over the stream like any other change. **There are no optimistic updates.**

Why: the four screens in the first slice (the line, the ticket graph, live build, the review desk) are the most interactive and animated in the design. React's keyed reconciliation keeps the node you clicked instead of replacing it, so principle 12 (focus stays where you clicked) holds under a stream of updates for N concurrent sessions without per-handler care. The prototype already needed a hand-rolled workaround for that at `live-build.html:256`. The motion in principle 9 is enter/exit and SVG-path animation, which Motion does with one `prefers-reduced-motion` switch. The browser never folds or derives anything, because the server holds every truth, so the client store stays a plain map by id.

## Considered options

- **Server-rendered HTML fragments over SSE, morphed into place** (Jinja plus idiomorph, or htmx or Datastar). This means one language, one template per piece, no build step and no API contract. Rejected: each animation and the interactive graph would become a hand-written JS island, and the graph's layout, selection and pan are exactly where a component model pays for itself.
- **JSON over SSE applied by vanilla JS,** continuing the prototype. Rejected: every piece is rendered twice (template and JS), and every handler has to protect focus by hand.
- **Next.js or Remix.** Rejected: Python is the server, and nothing needs server-side rendering.
- **Optimistic updates.** Rejected: the server is local, so the round trip is milliseconds, and a second copy of the truth in the browser is the drift ADR-0003 exists to prevent.

## Consequences

**A shape is defined once, in Python.** Pydantic models define the API and every SSE event (one `WireEvent` union listed in the schema). FastAPI publishes them as OpenAPI, and `openapi-typescript` generates `web/src/api.gen.ts`, which is checked in, with CI failing on drift.

**Users never need Node.** A hatch build hook runs the Vite build into the Python package, so the wheel carries the bundle. During development, Vite's dev server proxies `/api` to the Python process.

**The visual language stays ours.** The prototype's CSS ports as the global design system, and components style themselves with CSS Modules over its tokens. The ticket graph uses elkjs for layout only and our own SVG for drawing, not a graph widget with its own look.

**Principle 12 becomes a test.** Playwright dispatches a real click, asserts `document.activeElement`, and sends a key press while recorded session files stream through the real server.

Decided in [The stack, and what happens to the prototype's HTML](https://github.com/jeffrichley/wayfarer/issues/9).
