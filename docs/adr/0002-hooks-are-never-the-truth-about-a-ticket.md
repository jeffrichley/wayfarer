---
status: stable
type: adr
---

# Hooks are never the source of truth about a ticket

Every fact the cascade acts on (claimed, PR open, reviewed, landed, blocked) is read back from GitHub or git after Wayfarer writes it there, even when a hook has just reported that fact in-process. Hooks supply only what GitHub cannot hold: that a run is live, its stage, its beats, and its Outcome up to the moment it is written to GitHub. The test for any new fact is: **would a restarted Wayfarer need this to decide the next move?** If so, it lives on GitHub.

Why: GitHub is the record, and Wayfarer keeps no second copy of workflow state that could drift. A run's `run_end` arrives first and is the tempting signal to cascade from. But a Wayfarer that died and restarted has lost every hook it saw, and it must make the same next move as one that never stopped. So on restart it rebuilds everything that matters from GitHub, uses the per-run event files for history only, names any run it started that never finished, and offers `DockerSandbox.reap(run_id)` without recovering the work.

## Consequences

This costs a round trip to GitHub between a run ending and its dependents starting, and it makes freshness of the GitHub read model part of the cascade's latency. A verdict computed from hook evidence, such as "this run never ran its skill", has to be written to GitHub before anything may act on it.

Decided in [The seam: how Wayfarer and Waystation share a process](https://github.com/jeffrichley/wayfarer/issues/4).
