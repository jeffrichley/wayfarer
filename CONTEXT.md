# Wayfarer

Wayfarer follows work as it moves through the mattpocock/skills workflow on one GitHub repo, and lets a person steer the agents doing it. The words below come from the skills themselves wherever the skills already have a word. Waystation has a glossary of its own, correct for a library that knows nothing of tickets or GitHub, and the two are not unified. Where a Wayfarer word names something Waystation carries out, its entry names Waystation's word too, so a reader can cross between them.

## The two names

**Wayfarer**:
This app: the web UI that follows work along the skill line and steers the agents doing it.
_Avoid_: Waystation (that is the library), the dashboard, the console

**Waystation**:
The sister Python library (`jeffrichley/waystation`) that Wayfarer runs on: primitives for orchestrating sandboxed agent runs against a git repo. It speaks only git and knows nothing of GitHub.
_Avoid_: the backend, the engine, the orchestrator

## The workflow

**Skill line**:
The fixed order work moves through: `/wayfinder` → `/to-spec` → `/to-tickets` → `/tdd` → `/code-review` → merge.
_Avoid_: pipeline, workflow stages, columns

**Station**:
One stop on the skill line, named for its skill and for what it produces ("Chart the way", "Write the spec", "Slice into tickets", "Build", "Review", "Landed").
_Avoid_: stage, step, status column

**Effort**:
One body of work travelling the skill line, from a loose idea to landed code. It usually starts as one map.
_Avoid_: project, epic, initiative

**Repo**:
One GitHub repository Wayfarer is connected to. A repo holds many efforts. Wayfarer works against a local clone of it, which Waystation calls the host repo.
_Avoid_: workspace, project

## Charting (`/wayfinder`)

**Map**:
The GitHub issue labelled `wayfinder:map` that charts one effort: its destination, notes, decisions so far, fog and out-of-scope work.
_Avoid_: plan, roadmap, parent issue

**Destination**:
What reaching the end of a map looks like: a spec, a decision, or a change made in place. It fixes the map's scope.
_Avoid_: goal, objective, outcome

**Decision ticket**:
A child issue of a map that asks one question whose answer is a decision. It has one of four types: research, prototype, grilling or task.
_Avoid_: task (except for the task type), subtask

**HITL / AFK**:
Whether a ticket resolves only in a live exchange with a person (HITL, human in the loop) or can be driven by an agent alone (AFK).
_Avoid_: manual/automatic, interactive/background

**Claim**:
The assignee on an open ticket, which marks it as taken by a session.
_Avoid_: lock, owner

**Frontier**:
The open, unblocked, unclaimed tickets on a map, or on an effort's ticket graph: the edge of what is known. A ticket on it is **takeable**. A ticket is unblocked once every ticket blocking it is closed, whether or not that ticket landed. An Asked ticket is never on it.
_Avoid_: ready queue, backlog, todo

**Fog**:
Work in scope that can't yet be stated sharply enough to be a ticket. It lives in the map's "Not yet specified" section.
_Avoid_: backlog, unknowns, ideas, TBD

**Graduate**:
When fog becomes one or more tickets, or dissolves into none, because a resolution made it specifiable.
_Avoid_: promote, convert

**Resolution**:
The comment that answers a decision ticket, posted when the ticket closes.
_Avoid_: answer, outcome, result

**Out of scope**:
A ticket ruled beyond the destination. It is closed, never graduates, and never counts as a decision.
_Avoid_: won't do, cancelled, deferred

**The way is clear**:
The moment a map has no open tickets and no fog left. The map is done, and the effort moves to the next station.
_Avoid_: complete, finished, 100%

**Charting**:
The one session that names a destination, maps the frontier and creates a map. It resolves no tickets.
_Avoid_: planning session, setup

## Specs and tickets

**Spec**:
The issue `/to-spec` writes from what has been decided: problem, solution, user stories, implementation decisions, testing decisions and out of scope. It is labelled `ready-for-agent`.
_Avoid_: PRD, design doc, requirements

**Seam**:
The interface a feature is tested through. `/to-spec` proposes seams and a person agrees them. One seam is ideal.
_Avoid_: boundary, test layer

**Story coverage**:
How many of a spec's user stories have a ticket that delivers them.
_Avoid_: progress, completion

**Ticket**:
A tracer-bullet slice from `/to-tickets` that cuts through every layer and is small enough for one agent session. It declares which tickets block it.
_Avoid_: card, task, story

**Blocking edge**:
A "blocked by" link between two tickets. It uses GitHub's native dependency where one exists.
_Avoid_: dependency arrow, link

**Prefactor**:
A ticket that reshapes existing code so later tickets become easy. It comes first.
_Avoid_: refactor ticket, tech debt

**Acceptance criterion**:
One checkable condition a ticket must meet.
_Avoid_: requirement, AC, checklist item

## Building and reviewing

**Session**:
One Claude Code run working one ticket, with one skill or purpose: an `/implement` build (which runs `/tdd` and `/code-review` itself), a resolver session, a retry. A ticket may have several over its life. Waystation calls this a run.
_Avoid_: job, run, agent instance, worker

**Image**:
The container every session runs in: Wayfarer's base, holding the skills and the agent, plus the repo's own layer, holding its toolchain. A repo without a layer cannot start sessions.
_Avoid_: sandbox (Waystation's word for the running container), environment, box

**Start gate**:
What must hold before any session starts: an image that is current and has passed its probe, a credential for the agent, a read-only GitHub token so a session can read its own ticket, and a git identity. Failing it pauses the cascade and raises one item in Needs you.
_Avoid_: readiness (that is about a repo's skills and tracker), preflight (Waystation's per-run check), health check

**Outcome**:
The structured report a session hands back when it ends. It is the only way a session can reach a person, since nothing flows into a running one. Borrowed from Waystation unchanged.
_Avoid_: result, response, summary

**Resolver session**:
A session that replays a ticket's preserved commits onto the effort branch, resolving conflicts one commit at a time. Nothing but its purpose sets it apart from any other session. Waystation calls this a resolver run.
_Avoid_: resolver run, merger, fixer, conflict handler

**Preservation branch**:
The branch that keeps a session's commits whenever they did not land: the session failed, or its work conflicted. Nothing a session produced is lost. Borrowed from Waystation unchanged.
_Avoid_: backup branch, conflict branch

**Beat**:
One meaningful moment in a session, derived from what the agent did: a read, a remark, a red test run, a green test run, a refactor, or the outcome it reported. Several tool calls can make one beat.
_Avoid_: log line, event, message, step

**Remark**:
A beat carrying the agent's own narration of what it is doing and why.
_Avoid_: note (that is a person's message to a session), thought, reasoning

**Red / green**:
A failing or passing test run. In `/tdd` a red always comes before its green.
_Avoid_: fail/pass (in the UI), broken/fixed

**Cycle**:
One red → green turn in a session, with any refactor that follows while the tests stay green. A session's beats are grouped by cycle, after an opening orient.
_Avoid_: iteration, loop, chapter

**Note**:
A message a person leaves for a running session. The session reads it before its next step, without stopping. Not in the first slice: nothing can flow into a running session.
_Avoid_: comment, prompt, chat

**Question**:
Something a session ended to ask a person, because only they can decide it. It lives on the ticket, and answering it resumes the session where it stopped. A blocking finding the session left unfixed is one too, though answering a finding does not yet resume anything. A session never waits to be answered.
_Avoid_: blocker, alert, escalation

**Axis**:
One of the two things `/code-review` checks a change against in parallel: **Standards** (the repo's coding standards) and **Spec** (what the ticket and spec asked for).
_Avoid_: check, lint, review type

**Finding**:
One gap `/code-review` reports on an axis. A finding is **blocking** (anything on Spec, or a breach of a standard the repo documents) or a **judgement call** (a heuristic, such as a suspected smell). A blocking finding the session leaves unfixed holds its ticket from landing until a person decides. It is a question the session asks by ending.
_Avoid_: issue, comment, error, nit

**Ticket branch**:
The branch one ticket's commits are collected on before they land. Named for the ticket, cut from the effort branch. It is what a person sees of where a session worked; the session's own copy of the repo is never shown, because nothing can be done with it.
_Avoid_: worktree, workspace (Waystation's word for a run's private copy, which lives and dies inside the sandbox), session branch

**Effort branch**:
The branch one effort's tickets land on. Dependents branch from it, so an agent builds on what its blockers produced. It meets the trunk once, when the effort ships.
_Avoid_: feature branch, integration branch, staging branch

**Merge queue**:
The ordered line of finished tickets waiting to land on the effort branch. It exists because two tickets that each pass alone can break once both land.
_Avoid_: merge train, batch, landing queue

**Held**:
A finished ticket kept back from landing until a person decides, because its session left a blocking finding or did not finish. The person lets it land, fixes it, or closes it.
_Avoid_: draft (that is a `/to-tickets` draft), blocked (that is a ticket waiting on another), stuck, failed

**Asked**:
An unfinished ticket whose session ended to ask a question. It stays claimed and waits on a person. Answering resumes the same session in a fresh container, as a continuation rather than a new start.
_Avoid_: paused (nothing is running), held (that is a finished ticket), blocked, waiting

**Landing**:
A finished ticket whose work is in the merge queue: waiting its turn, or being re-tested against the latest effort branch. It is moving, not waiting on anyone.
_Avoid_: queued, merging, pending, in review (that is waiting on a person)

**Landed**:
A ticket whose commits have reached the effort branch. Landing closes the ticket, and the close is what unblocks its dependents.
_Avoid_: done, closed, merged, shipped

**Cascade**:
An effort's tickets starting themselves as they reach the frontier, once a person arms it. **Armed** means it starts each takeable ticket, up to the repo's cap, and resumes each Asked ticket once answered. A resume is not a start. **Paused** means it starts nothing new while running sessions finish. It disarms itself when every ticket in the effort is closed.
_Avoid_: autopilot, auto-run, queue (that is the merge queue)

**Shipped**:
An effort whose branch has merged into the trunk, reviewed by a person once. The only human gate in a cascade.
_Avoid_: released, delivered, done

## Wayfarer's own words

**Course**:
The route an effort has actually walked so far. It is the only thing drawn in the accent colour, apart from each screen's one primary action.
_Avoid_: progress bar, path, timeline

**Thread**:
One ticket's lineage traced from the map decision it came from, through its spec story, its session and its PR, to landed.
_Avoid_: history, breadcrumb, audit trail

**Chronicle**:
The running account of what happened across the repo, written as sentences and naming things by name.
_Avoid_: activity feed, log, notifications

**Needs you**:
Everything waiting on a person, ordered by how much it unblocks: reviews, questions, HITL tickets, seams, drafts to check.
_Avoid_: inbox, notifications, to-do, alerts

**Desk**:
The screen where you work through Needs you.
_Avoid_: inbox, review queue

**Replay**:
Scrubbing a map back through its history to watch fog clear and decisions land.
_Avoid_: timeline, history view, undo

**Handoff**:
The moment an effort's course moves from one station to the next, most visibly when the way is clear and `/to-spec` takes over.
_Avoid_: transition, export, promotion

**Readiness**:
Whether a repo has what each station's skill needs: the skill installed, the tracker configured, labels and domain docs present.
_Avoid_: setup status, health, onboarding checklist
