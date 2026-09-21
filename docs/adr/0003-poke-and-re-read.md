---
type: adr
title: Wayfarer hears from GitHub by poke-and-re-read, and a webhook is only a poke
status: stable
---

# Wayfarer hears from GitHub by poke-and-re-read, and a webhook is only a poke

The GitHub read model runs on one internal signal: **something may have changed, so re-read**. Nothing it receives is ever applied as data. Three sources raise that signal:

1. **Wayfarer's own writes.** Straight after it claims, opens a PR, posts findings or merges, it re-reads what it touched. Most transitions in a cascade are Wayfarer's own, so the cascade's steps become an immediate round trip rather than a wait for the next poll.
2. **A conditional poll**, the only outside source in the first slice. A `GET /repos/{o}/{r}/issues?since=…&sort=updated` with an `ETag` runs every 10 s while a cascade is armed or a browser is open, and every 60 s otherwise. It respects `X-Poll-Interval` and backs off on `403`/`429`. A PR's checks do not bump its issue, so each PR the cascade is waiting on gets a conditional check of its own on the same rhythm.
3. **A webhook**, deferred ([Webhooks as a poke](https://github.com/jeffrichley/wayfarer/issues/18)). It arrives through a tunnel the person runs, and when it is live the poll slows to reconciliation.

When the signal fires, **one read model** re-reads the effort's whole ticket graph in a single GraphQL query (about 3 points for 30 tickets, against 5,000 an hour), and it serves both the screens and the cascade.

Why: Wayfarer runs locally, so a webhook has no address to arrive at without a tunnel, and a tunnel that is down loses deliveries for good. Polling was the worry: surely it is unfriendly to GitHub. It isn't, when done conditionally, because GitHub states that a `304` "does not count against your primary rate limit". So the poll costs latency, about 10 s on changes made outside Wayfarer, and not goodwill. Treating a webhook as a poke keeps it under the same rule ADR-0002 applies to hooks: only a read of GitHub is believed.

## Considered options

- **Webhooks as the primary source.** Rejected for now: it needs repo admin, a public URL and secret handling, and it still needs a reconciling read for everything missed while down.
- **`gh webhook forward`.** Rejected: GitHub documents it as "only designed for use during testing and development", with one forwarder per repo.
- **A narrower, faster watch for the cascade beside the screens' read model.** Rejected: a full read costs about 3 points, so a narrow watch saves nothing worth having, and two models could disagree.
- **The repo events API as the change probe.** Rejected: GitHub gives its latency as "anywhere from 30s to 6h".

## Consequences

A webhook can be added later without touching the read model. It is just a new source of the same signal. The poll never goes away.

Decided in [The GitHub read model: freshness, and what Wayfarer keeps of its own](https://github.com/jeffrichley/wayfarer/issues/6).
