---
type: reference
status: draft
---
# Data and commands

This doc covers where everything on screen comes from, and what every steering action has to do in the real build. The prototype fakes both with sample data in `assets/wayfarer.js`.

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
| Wayfarer's own store | Only what nothing else holds. See [The store](#the-store-decided). |

**Principle:** GitHub is the record. Waystation derives state and never keeps a second copy of workflow state that could drift from the tracker.

## Freshness *(decided)*

Wayfarer hears from GitHub by **poke-and-re-read** ([ADR-0003](../adr/0003-poke-and-re-read.md)). One signal, *something may have changed*, triggers a re-read, and nothing Wayfarer receives is applied as data.

- **Its own writes** trigger an immediate re-read of what they touched.
- **A conditional poll** (`issues?since=…&sort=updated` with an `ETag`) runs every 10 s while a cascade is armed or a browser is open, and every 60 s otherwise. A `304` costs no rate limit. It respects `X-Poll-Interval` and backs off on `403`/`429`.
- **PR checks** don't bump the issue, so each PR the cascade is waiting on is polled for its checks on the same rhythm.
- **Webhooks** are deferred ([Webhooks as a poke](https://github.com/jeffrichley/wayfarer/issues/18)): a poke through a tunnel the person runs, never data, and never a replacement for the poll.

**One read model** serves the screens and the cascade: a single GraphQL read of the effort's ticket graph per change (about 3 points for 30 tickets).

**When GitHub and a live session disagree, GitHub owns the state.** A live session only annotates the card with its stage, its last beat, or "session ended, waiting for GitHub to confirm". A state never advances on a hook alone ([ADR-0002](../adr/0002-hooks-are-never-the-truth-about-a-ticket.md)). If GitHub shows a ticket landed or closed while a session is still live on it, the card shows GitHub's state and the session is flagged in Needs you. It is not stopped automatically.

## The store *(decided)*

One SQLite file per repo (stdlib `sqlite3`, WAL), outside the checkout, at `~/.local/share/wayfarer/<owner>/<repo>/`, beside the per-run event files. It holds only what a restarted Wayfarer needs and GitHub cannot hold:

- **Sessions Wayfarer started:** run id, ticket, purpose, started, ended, event file, and the Outcome. Recorded at `run_start`, since Waystation generates the run id and nothing in the library writes it down.
- **Armed cascades:** which effort, and whether it is paused.
- **Last visit**, for the home headline. Updated on leaving home, so a refresh keeps the headline.
- **Settings**, per repo. The concurrency cap, default 3, is one number shared by every armed cascade. Auto-merge on green is on by default. A PR with no checks at all counts as green, since the effort's own PR into the trunk is where the repo's gates apply. Any pending check waits, and any failing check goes to Needs you. Session time caps default to 20 min of silence and 2 h of wall time, with no cap on turns or dollars. The merge queue's re-test is capped at 30 min of wall time, with no silence cap; hitting it counts as a failed re-test.

Notes and queued agents are gone. Notes had nowhere to go once mid-run steering was cut, and an armed cascade replaces a per-ticket queue.

**Event files.** Wayfarer owns retention, since Waystation's `EventLog` has none. A session's JSONL file is kept until its effort ships, then deleted. The Outcome stays in the store.

**Restart.** Read the store, then GitHub, then Docker containers labelled `waystation.run-id`.
- A stored session with no end is an **orphan**. It appears in Needs you, naming its ticket, and is offered `DockerSandbox.reap(run_id)`.
- A labelled container with no store row is shown as unknown and never reaped automatically. The label carries no repo, so it may belong to another repo's Wayfarer.
- An armed cascade comes back **paused**, so a restart never spends money unasked.

**Questions.** A session asks with `AskUserQuestion`, and a hook in the image defers the call, which ends the session ([Ask by ending](https://github.com/jeffrichley/wayfarer/issues/19)).
- **On GitHub:** a question comment on the ticket, carrying a hidden marker naming the session, plus the `wayfarer:asked` label. That is the whole state.
- **Answering:** removing the label is the signal, whether the person answered in the desk or on GitHub.
- **Locally:** the session's transcript is a file beside its event files, with the same retention. If it is lost, the resume starts cold with the question and answer in its prompt.

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
  2. labelled `wayfarer:asked` → **asked**
  3. labelled `wayfarer:held` → **held** (a draft PR when the session left commits, a comment when it left none)
  4. PR ready (not draft), checks green or absent, and approved when auto-merge is off → **landing**. Approved is an approving GitHub review, or a **Land it comment** on the ticket naming the PR in a hidden marker, written by the person whose token Wayfarer holds. Wayfarer enqueues every such ticket it is not already landing, so a restart rebuilds the merge queue from GitHub in PR-ready order
  5. PR open → **in review**
  6. a session running → **building**
  7. every blocker landed and nobody on it → **takeable**
  8. otherwise → **blocked**

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
| In review | Auto-merge is off and a clean, green PR is waiting for approval |
| Question | A ticket is Asked: labelled `wayfarer:asked` |
| Held | A ticket is labelled `wayfarer:held`: a blocking finding, a failed attempt, or work that could not land (a red re-test on the latest effort branch, or a conflict a resolver session couldn't clear), said in plain words |
| Environment | A session failed for a reason that was not its own, and the cascade paused. A ticket that had not reached Landing went back on the frontier; a Landing ticket keeps its place in the merge queue. One item also covers an effort branch whose own tests are red |
| Drafts | `/to-tickets` drafts are waiting for the person to check them (its "quiz the user" step) |
| Ship the effort | Every ticket in an effort is closed and the cascade has disarmed |
| Orphan container | A container labelled with a run id outlived its session, and is offered for `reap` |
| Closed with a live session | GitHub closed a ticket whose session is still running |

Grilling and prototype tickets and seams are not in this slice: those stations are out of scope.

**Ordering.** Decided in [What "most unblocking first" computes in Needs you](https://github.com/jeffrichley/wayfarer/issues/24).
- **One list** across every effort in the repo, each item naming its effort on the right.
- **Environment** is pinned above everything, unscored. It pauses every cascade, and there is only ever one.
- **Everything else that concerns a ticket** ranks by what it **holds up**: the item's ticket plus every open ticket downstream of it, since a cascade would work all of them the moment it could. A ticket stalled by two items counts in both; nothing ever adds the counts up. A draft counts every ticket in it.
- **Items that hold up no ticket** come last: Ship the effort, then orphan containers, then closed tickets with a live session.
- **Ties** go to whatever has waited longest.
- **On the desk the order freezes** while you work. Counts and sentences update live, new items join at the bottom marked new, and it re-ranks when you come back. Home always shows the live order.
- **Sentences** are templated, with the reason or question first:

  | Kind | Sentence |
  |---|---|
  | Environment | "Every cascade is paused · ⟨plain-words reason⟩" |
  | Question | "⟨question's gist⟩ · Holds up N tickets" |
  | Held | "⟨plain-words Held reason⟩ · Holds up N tickets · M start when it lands" |
  | In review | "Clean and green, waiting on your approval · Holds up N tickets" |
  | Drafts | "N tickets drafted from ⟨spec⟩, waiting on your check" |
  | Ship the effort | "Every ticket landed · one review to ship ⟨effort⟩" |
  | Orphan container | "A container from ⟨ticket⟩ outlived its session" |
  | Closed with a live session | "⟨ticket⟩ was closed on GitHub while its session runs" |

  "M start" counts the tickets that become takeable the moment it resolves. When that is none, the clause is dropped.
- **The words.** "Holds up", never "unblocks": resolving a Held ticket may start nothing yet while still freeing everything behind it.

### Chronicle *(derived)*
Decided in [The chronicle](https://github.com/jeffrichley/wayfarer/issues/22).
- **Source:** a pure function of the effort's GitHub issue and PR timelines, plus the session rows already in the store. Nothing new is stored, so a rebuild gives the same chronicle. Facts that live only in Wayfarer, such as a paused cascade, appear in Needs you while live and never in the chronicle.
- **Sentences:** templated, one template per event kind. Where a line needs prose it quotes text that already exists: the question's gist, the plain-words Held reason, the first sentence of the Outcome summary. No model writes lines.
- **What earns a line:** a ticket taken, Asked (with the question's gist), answered and resumed, Held (with the reason), retried (Continue or Start over), landed (with what it unblocked), closed without landing; a cascade armed; an effort ready to ship, and shipped; tickets published by `/to-tickets`. **Never:** beats, which skill is running, a PR opening, entering the queue, re-testing, a resolver session (these show on the card while Landing, and reach the chronicle only as the Held or Landed they end in), CI runs, label noise.
- **Folding, by cause:** a line is one landing, answer, arming or publish plus what it *directly* caused: the tickets it made takeable and the sessions the cascade started on them. A ticket assigned after its last blocker closed folds into that blocker's line. Unrelated events are never folded by time. A line is at most two sentences; any overflow gets its own line.
- **Who acted:** by kind of event, not by the timeline's actor, since Wayfarer writes with the person's token. Automatic kinds (taken, landed, Held) read passively; a person's kinds (answered, let it land, retried, closed without landing, armed) read "You". An assignment with no session row in the store is a person taking the ticket. Wayfarer closes a landed ticket with a comment ("Landed on ⟨effort branch⟩ at ⟨sha⟩") carrying a hidden marker, so a close without one is a person's. Any other login is named.
- **Each line** shows the time, a status glyph, the sentence, and the effort's name on the right. Not the skill.
- **Paging:** Today and Yesterday on home, then Earlier one day at a time. A shipped effort's lines stay, ending with "⟨effort⟩ shipped". Nothing is cached beyond memory.
- **Home headline and standfirst:** templated, separately from the chronicle, from the same events since the last visit. The headline is under 14 words and leads with the top Needs you item, then landings. The standfirst is one sentence per active effort, from its counts. The last visit is local to this machine and is updated on leaving home, not on arriving.

## Commands (steering)

Each command lives in the prototype at the `data-piece` shown. "Must do" is the real effect. Every command also updates the read model, so every screen reflects it.

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
| Start an agent on this ticket | `start-agent`, `start-agent-132` | Superseded: arming a cascade is the only way a session starts | Cut ([The cascade](https://github.com/jeffrichley/wayfarer/issues/14)) |
| Arm a cascade | none yet | Confirm in one line ("4 tickets are takeable now, up to 3 at a time"), then start each takeable ticket: assign it, then submit its flow | [The cascade](https://github.com/jeffrichley/wayfarer/issues/14) |
| Pause / Resume the cascade | none yet | Stop submitting; running sessions finish. Resume submits again | [The cascade](https://github.com/jeffrichley/wayfarer/issues/14) |
| Stop a ticket | `POST /api/tickets/{n}/stop` | Cancel its session with salvage. The ticket stays claimed and is Held, its work on a draft PR, or a comment when it had none | [The cascade](https://github.com/jeffrichley/wayfarer/issues/14) |
| Retry a Held ticket | `POST /api/tickets/{n}/retry` with `{"start": "continue" \| "start_over"}` | Clear `wayfarer:held` and start a session, as the person's start: it runs while the cascade is paused, and never spends the automatic start. **Continue** (the default when there are commits) goes on from the PR's head, or else the preservation branch, resuming the transcript, or starting cold with why it stopped when the transcript is lost. **Start over** runs on the effort branch's head and closes the draft PR, keeping the preservation branch. It is the default for a ticket Held by a red re-test, since continuing would build on the version that broke. A retry the environment fails is Held again, not released | [The unhappy path of a session](https://github.com/jeffrichley/wayfarer/issues/20), [When a session goes wrong](https://github.com/jeffrichley/wayfarer/issues/41) |
| Queue an agent for when it unblocks | `queue-agent` | Superseded by arming a cascade for the effort, which starts every ticket as it becomes takeable | Wayfarer's store (armed cascade) |
| Pause / Resume a session | `pause-session` | Pause the session at its next safe point, then resume it | Cut: nothing flows into a running session |
| Send note | `send-note` | Deliver a note the session reads before its next step, without stopping it | Transport open |
| Open terminal | `open-terminal` | Open the worktree's session in a real terminal | Open |
| Send answer and resume | `send-answer-<n>` | Post an answer comment on the ticket, remove `wayfarer:asked`, and queue a resume: a fresh container on the preservation branch runs `--resume` with the stored transcript, and the hook hands the answer to the deferred `AskUserQuestion` call | [Ask by ending](https://github.com/jeffrichley/wayfarer/issues/19) |
| Send finding to the agent | `send-finding` | Reopen the ticket's session with the finding as its task | Transport open |
| Comment on a diff line | `pr-diff` rows | Post a PR review comment *and* deliver it to the worktree session | Transport open |
| Request changes | `request-changes` | Post a changes-requested review and reopen the session with the request | Transport open |
| Let it land | `POST /api/tickets/<n>/let-it-land` | For a Held ticket with a PR: mark the PR ready and remove `wayfarer:held`, so it joins the merge queue. Marking it ready by hand on GitHub does the same, and Wayfarer clears the label, so Wayfarer never leaves a hold on a ready PR (it drafts a PR before labelling it) | [The merge queue's unhappy path](https://github.com/jeffrichley/wayfarer/issues/21), [#108](https://github.com/jeffrichley/wayfarer/issues/108) |
| Land it | `POST /api/tickets/<n>/land-it` | With auto-merge off, approve a clean, green PR in review so it joins the merge queue. Not a GitHub review: Wayfarer writes with the person's token, so the person authored the PR and GitHub refuses their approval (422). It posts a Land it comment on the ticket whose hidden marker names the PR, which counts as approval when the person whose token Wayfarer holds wrote it, and is not withdrawn by a later push, as a GitHub approval is not by default. An approving review on GitHub does the same. Merging by hand on GitHub skips the queue and is accepted as landed, untested | [The merge queue's unhappy path](https://github.com/jeffrichley/wayfarer/issues/21), [#108](https://github.com/jeffrichley/wayfarer/issues/108) |

## Global open questions

1. **Session transport:** how Waystation starts, watches and steers Claude Code sessions (hooks, the Agent SDK, or a wrapper), and whether it runs on the developer's machine or a server.
2. **Deployment:** a local app beside the repo, or a hosted web app with GitHub OAuth? The "watch and steer" choice and running sessions in local worktrees suggest local first.
3. **Several people:** "Needs you" assumes one person driving. What changes when a team shares a repo? Is "you" the assignee?
4. **The conventions above:** map → spec pointer, fog → ticket graduation, story → ticket, seam record. Should these be written back into the skills (upstream changes to mattpocock/skills) or kept as Waystation-side inference?
5. **Several repos:** the repo switcher implies it. Does "Needs you" roll up across repos?
6. **Freshness:** decided. Poke-and-re-read with a conditional poll, webhooks later. See [Freshness](#freshness-decided).
