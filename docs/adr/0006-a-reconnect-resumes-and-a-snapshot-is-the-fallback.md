---
type: adr
title: A reconnect resumes from the last event, and a snapshot is only the fallback
status: draft
generated:
  by: wayfarer/claude-opus-5.5
  at: 2026-09-23T01:11:39Z
---

# A reconnect resumes from the last event, and a snapshot is only the fallback

This refines ADR-0004, which says a page gets a snapshot "when it connects or reconnects". **A page that reconnects carrying the id of the last event it saw gets exactly the events it missed, and a snapshot only when those can no longer be replayed.** A page connecting for the first time still gets a snapshot.

The server numbers every change and keeps the most recent ones in a backlog bounded by the `stream_backlog` setting. An event's id is `<epoch>-<count>`, with the epoch drawn when the process starts. A reconnect gets a snapshot instead of a replay when its id is from another epoch (Wayfarer restarted), is not an id at all, or is older than the backlog reaches. A page that falls too far behind while connected gets a snapshot the same way. An upsert of an item exactly as the page already holds it is never sent.

Why: the ticket that built the stream ([One SSE stream, and commands that return nothing](https://github.com/jeffrichley/wayfarer/issues/31)) asks that reconnecting "resumes from the last event seen and never loses or duplicates what happened in between". A snapshot on every reconnect loses nothing either, but it resends everything the page already holds. Resuming sends only what is new, and falls back to the snapshot wherever it cannot be exact, so a page never has a gap and never sees an event twice.

## Considered options

- **A snapshot on every reconnect,** as ADR-0004 wrote it. Rejected: it ignores the `Last-Event-ID` the browser already sends, and resends the whole store after every blip.
- **An unbounded backlog.** Rejected: every bound is a named setting, and a snapshot is a cheap, exact answer for a page that missed a lot.

## Consequences

The browser does nothing to resume: `EventSource` sends `Last-Event-ID` by itself, and the page applies the replayed events like any others.

Reached while building [#31](https://github.com/jeffrichley/wayfarer/issues/31); a draft until the user agrees it.
