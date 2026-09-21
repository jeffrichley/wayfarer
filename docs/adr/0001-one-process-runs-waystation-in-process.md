---
status: stable
type: adr
---

# One process runs Waystation in-process, and a ticket is its own run in a continuous queue

Wayfarer is one async Python process. It imports Waystation, serves HTTP on the same event loop as every agent run, and attaches its own `HookBundle` to each run. It writes no flow script to disk. The cascade submits each ticket as **its own run** into a continuous queue the moment the ticket is takeable. Live traffic reaches the browser over SSE, and an append-only JSONL file per run is the replay source for a browser that reconnects.

Why: Waystation serialises writes to host git with a lock that is **per event loop, inside one process** (Waystation ADR-0033). Only a single process gets serialised landings for free across runs of every kind (`/tdd`, `/code-review`, resolver runs) running at once. The hooks already hand over parsed `AgentText` / `AgentToolUse` objects, so a subprocess boundary would only re-serialise them.

## Considered options

- **A web server that launches flow scripts as subprocesses and reads an event stream they write out.** Rejected: separate processes integrating into one checkout are not serialised against each other. It also buys a crash boundary that does not help, since a run dies with its parent either way.
- **One long `fan_out` for the life of the cascade.** Not possible: `fan_out` reads its whole iterable before anything starts, so a batch cannot grow.
- **A `fan_out` per wave of newly takeable tickets.** Rejected: the grouping means nothing to the domain, a cap would apply per wave, and stopping everything would mean tracking every wave in flight.
- **WebSocket or polling to the browser.** Rejected: nothing flows into a running agent, so a bidirectional channel is wasted, and polling would make the at-work view visibly lag.

## Consequences

**Waystation ADR-0003 is not breached.** It says a flow is Python the user owns. Wayfarer is a user of the library, and its scheduler is its own flow, written against the public API. A person who wants to write flows by hand is served by a teaching export instead.

**The continuous queue belongs in Waystation.** It is filed as [waystation#113](https://github.com/jeffrichley/waystation/issues/113). Until it ships, Wayfarer's stand-in is built on the public `preflight(specs)` and `spec.perform(preflighted=True)` (Waystation ADR-0032), with the same interface: submit a spec, iterate results as they complete, an optional cap, and `async with` to stop. Swapping in the real queue is then a deletion. Each run is preflighted when it starts, not when it was queued.

The shape supports three stop behaviours with nothing more from the engine:
- **Stop one ticket:** cancel its run, with salvage still shielded.
- **Stop everything:** exit the queue's block, so in-flight runs are cancelled with salvage and queued runs never start.
- **Pause:** stop submitting, and let running runs finish.

Whatever serves HTTP has to be async and share the loop.

Decided in [The seam: how Wayfarer and Waystation share a process](https://github.com/jeffrichley/wayfarer/issues/4).
