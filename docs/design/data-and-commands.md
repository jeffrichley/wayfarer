# Data and commands

This doc covers where everything on screen comes from, and what every steering action has to do in the real build. The prototype fakes both with sample data in `assets/waystation.js`.

Each part is marked as one of three kinds, and they need to stay distinct:
- **Defined by the skills:** the skill's `SKILL.md` already says how this is stored. Read it and follow it.
- **Proposed convention:** the skills don't record this, but a screen depends on it. Waystation needs a convention, or has to infer it. Grill the user before choosing.
- **Open:** not decided.

## Sources

| Source | Gives |
|---|---|
| GitHub Issues, through the tracker `/setup-matt-pocock-skills` recorded in `docs/agents/issue-tracker.md` | Maps, decision tickets, specs, build tickets, labels, assignees, blocking edges, comments, timelines |
| GitHub pull requests and checks | PRs, diffs, CI status, merges |
| The repo itself | Installed skills, `docs/agents/*`, `CONTEXT.md`, ADRs (these give readiness) |
| Claude Code sessions in git worktrees | Running work: beats, test runs, questions, changed files |
| Waystation's own store | Only what nothing else holds: per-user "last visit" for the home headline, queued agents, notes waiting to be read. Keep it minimal. |

**Principle:** GitHub is the record. Waystation derives state and never keeps a second copy of workflow state that could drift from the tracker.

## The read model

### Repo readiness *(defined by the skills, mostly)*
- **Issue tracker:** `docs/agents/issue-tracker.md` exists.
- **Triage labels:** `docs/agents/triage-labels.md` exists (only when the `triage` skill is installed). `ready-for-agent` exists.
- **Domain docs:** `CONTEXT.md` or `CONTEXT-MAP.md`; count the ADRs under `docs/adr/`.
- **Wayfinder labels:** `wayfinder:map` and `wayfinder:research|prototype|grilling|task` exist. These are created with the first map.
- **Skills installed:** each station's skill is present. *Open:* where to look (`.claude/skills`, a plugin, a user-level install).

### Map *(defined by `/wayfinder`)*
- **What it is:** an issue labelled `wayfinder:map`. Its body has the sections Destination, Notes, Decisions so far, Not yet specified, and Out of scope.
- **Decisions so far:** closed child tickets, gisted in the map body.
- **Fog:** the entries under "Not yet specified".
- **The way is clear:** no open child tickets *and* an empty "Not yet specified".
- **Destination kind** (spec, decision or change) decides the next station after the way is clear. *Proposed convention:* read it from the Destination wording, or ask once. *Open.*

### Decision ticket *(defined by `/wayfinder`)*
- **Structure:** a child issue of the map, with a `wayfinder:<type>` label and a `## Question` body.
- **Mode:** research is AFK, prototype and grilling are HITL, and task can be either. *Open:* how a task records its mode.
- **Claim:** the assignee. **Blocking:** GitHub's native issue dependencies.
- **State on the map, in order:**
  1. closed and listed under Out of scope → **out of scope**
  2. closed → **decided** (the resolution is its closing comment)
  3. assigned → **claimed**
  4. any blocker open → **blocked**
  5. HITL → **waiting on you**
  6. AFK → **frontier**
- **Graduated from fog:** *proposed convention.* The skill removes the fog line and creates the ticket, but records no link between them. The map screen shows "Graduated from fog" on a ticket, so Waystation needs either a pointer written at graduation or an inference from the map body's edit history. *Open.*
- **Replay history:** from issue timelines: children created, assigned and closed, and edits to the map body's fog and out-of-scope sections. Each event needs a one-sentence caption. *Open:* whether captions are generated or written by the session that made the change.

### Spec *(defined by `/to-spec`)*
- **Structure:** an issue labelled `ready-for-agent` using the spec template: Problem Statement, Solution, User Stories (a numbered list), Implementation Decisions, Testing Decisions, Out of Scope, Further Notes.
- **Map → spec pointer:** *proposed convention.* Neither skill records which map a spec came from. The handoff and the spec byline both need it. Suggest `/to-spec` (or Waystation, when it starts `/to-spec`) comments on the map with a link to the spec and closes the map.
- **Decision → implementation decision:** *proposed convention.* The spec reader traces each implementation decision back to a map ticket. Either the spec links ticket names inline, or Waystation matches them. *Open.*
- **Agreed seam:** *proposed convention.* It's the outcome of `/to-spec`'s "check with the user" step. It needs to be recorded in the spec, for example as a Testing Decision, so the spec reader can show "Seam agreed with you".

### Build ticket *(defined by `/to-tickets`)*
- **Structure:** an issue with a title, "what it delivers", acceptance criteria and blocking edges (native dependencies on GitHub). The first tickets may be prefactors.
- **Story → ticket:** *proposed convention.* Story coverage depends on knowing which stories a ticket delivers. Suggest a "Delivers stories 3, 4" line in each ticket body, written by `/to-tickets`.
- **Acceptance criterion → test name:** taken from the session (the test it wrote for that criterion) or from the PR. *Open.*
- **State:**
  1. PR merged or issue closed as completed → **landed**
  2. PR open → **in review**
  3. its session paused on a question → **waiting on you**
  4. a session running → **building**
  5. every blocker landed and nobody on it → **takeable**
  6. otherwise → **blocked**

### Session *(open: this is the biggest unknown)*
A Claude Code run on one ticket in `wt/<name>`. The screens need:
- **Beats:** reads, notes, red and green test runs (with output), refactors, questions, and your notes, each with a timestamp and the criterion being worked on.
- Live progress on acceptance criteria.
- Changed files with line counts.
- The ability to pause, resume, receive a note, and receive an answer.

*Open:* the transport. Candidates are Claude Code hooks writing an event stream, the Claude Agent SDK running sessions directly, or a wrapper process. Classifying raw tool calls into beats (which reads count, and what counts as a "note") is also open. The prototype's beats show the intended *granularity*: roughly one beat per meaningful step, not per tool call.

### Review *(defined by `/code-review`, with storage open)*
- **What it produces:** two parallel sub-agent reviews, Standards and Spec, each with findings.
- *Open:* where the findings are stored. PR review comments are the obvious place, and the desk needs each finding tied to a criterion and to a diff line.

### Needs you *(derived)*
An item appears when any of these is true:

| Kind | Condition |
|---|---|
| Review | A ticket's PR is open with `/code-review` done and awaiting a human |
| Question | A session is paused on a question |
| Grilling / prototype | A HITL decision ticket is on the frontier, or claimed by you and in session |
| Seam | `/to-spec` is waiting for seam agreement |
| Drafts | `/to-tickets` drafts are waiting for the person to check them (its "quiz the user" step) |

**Ordering:** by how much the item unblocks. Count the tickets whose *last* open blocker is this item, and add weight when resolving it would clear fog or clear the way. Each item states that effect in words.

### Chronicle *(derived)*
- **Contents:** one sentence per meaningful event, newest first, grouped by day, each naming things by name and tagged with its skill.
- **Home headline:** summarises events since the person's last visit (stored by Waystation).
- *Open:* whether sentences are templated or written by a model, and how events are merged ("Three tickets reached the frontier, and two agents picked them up").

## Commands (steering)

Each command lives in the prototype at the `data-od-id` shown. "Must do" is the real effect. Every command also updates the read model, so every screen reflects it.

| Command | Where | Must do | Status |
|---|---|---|---|
| Start charting | `start-charting` | Start a Claude Code session running `/wayfinder` with the loose idea (the chart-the-map mode) | Session transport open |
| Set the destination / map the frontier / sort ticket or fog | `set-destination`, `map-the-frontier`, `ticket-or-fog` | Relay the person's side of the charting grilling into that session. The sort result becomes the tickets and "Not yet specified". | Open: whether the sort is a UI or a conversation turn |
| Create the map | `create-map-button` | The session creates the map issue and child tickets, wires blocking in a second pass, and fires research subagents | Defined by `/wayfinder` |
| Start grilling session | `start-grilling` | Claim the HITL ticket for the person and open a `/grilling` + `/domain-modeling` session on it | Transport open |
| Post resolution and close | `close-last-ticket` | Post the resolution comment, close the ticket, append to the map's Decisions so far, and clear or graduate the fog the session named | Defined by `/wayfinder` |
| Agree seam and write the spec | `agree-seam` | Answer `/to-spec`'s seam check. `/to-spec` publishes the spec with `ready-for-agent`, and the map gets a pointer and closes. | Pointer convention proposed |
| Slice into tickets / Slice the uncovered stories | `slice-into-tickets`, `slice-uncovered` | Start `/to-tickets` on the spec (or on named stories). The drafts come back to the person before publishing. | Defined by `/to-tickets` |
| Publish tickets | `publish-drafts` | Publish the approved drafts with blocking edges and `ready-for-agent` | Defined by `/to-tickets` |
| Start an agent on this ticket | `start-agent`, `start-agent-132` | Claim the ticket, create `wt/<name>` from main, and start a Claude Code session running `/tdd` on it | Transport open |
| Queue an agent for when it unblocks | `queue-agent` | Waystation remembers the request and starts the session when the last blocker lands | Waystation store |
| Pause / Resume | `pause-session` | Pause the session at its next safe point, then resume it | Transport open |
| Send note | `send-note` | Deliver a note the session reads before its next step, without stopping it | Transport open |
| Open terminal | `open-terminal` | Open the worktree's session in a real terminal | Open |
| Send answer and resume | `send-answer-<n>` | Deliver the answer to the paused session, post it to the ticket as a comment, and resume | Transport open |
| Send finding to the agent | `send-finding` | Reopen the ticket's session with the finding as its task | Transport open |
| Comment on a diff line | `pr-diff` rows | Post a PR review comment *and* deliver it to the worktree session | Transport open |
| Request changes | `request-changes` | Post a changes-requested review and reopen the session with the request | Transport open |
| Approve and merge | `approve-merge` | Approve and merge the PR; the ticket lands, and dependents may reach the frontier | GitHub |

## Global open questions

1. **Session transport:** how Waystation starts, watches and steers Claude Code sessions (hooks, the Agent SDK, or a wrapper), and whether it runs on the developer's machine or a server.
2. **Deployment:** a local app beside the repo, or a hosted web app with GitHub OAuth? The "watch and steer" choice and running sessions in local worktrees suggest local first.
3. **Several people:** "Needs you" assumes one person driving. What changes when a team shares a repo? Is "you" the assignee?
4. **The conventions above:** map → spec pointer, fog → ticket graduation, story → ticket, seam record. Should these be written back into the skills (upstream changes to mattpocock/skills) or kept as Waystation-side inference?
5. **Several repos:** the repo switcher implies it. Does "Needs you" roll up across repos?
6. **Freshness:** GitHub webhooks, polling, or both, and how fast sessions have to feel live.
