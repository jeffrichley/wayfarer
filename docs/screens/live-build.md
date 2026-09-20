# Live build

**Prototype:** `live-build.html?session=<n>` · **Station:** `/tdd` · **Arrive from:** "Agents working" in the top bar, At work on home, Watch the session in the ticket graph, the thread · **Leave to:** the desk (review, questions), the ticket graph

## Intent

Several Claude Code sessions build tickets in parallel, each in its own worktree. Their raw output is terminal noise. This screen turns each session into a **story of red and green**: what it read, what test it wrote, whether the test failed first and then passed, what it refactored, and where it got stuck. It lets a person steer without taking over:
- leave a **note** the agent reads before its next step
- **pause** or resume
- **answer** a question

It answers: *is each agent doing the right thing, the right way, and does it need me?*

## Layout

Three columns under the top bar and route band (`/tdd` current):
1. **Lanes** (`session-lanes`), left: every session on this effort, plus the tickets around them.
2. **Story** (`session-story`), centre: the selected session's head, its beats, and the note composer (`nudge-composer`) pinned at the bottom.
3. **Evidence** (`session-evidence`), right: criteria, test rhythm, changed files, thread.

## Pieces

### Lanes (`lane-<n>`)
**"On the frontier · N sessions".** One button per session, showing:
- a glyph: building, waiting on you, or a thin ring if paused by you
- the ticket name
- mono meta: "wt/noise-floor · 41 min", "paused", or "paused by you"
- the **latest beat** in one or two lines. A question reads "Asked you: …" in ink.
- **criterion ticks:** one short bar per acceptance criterion, filled as each passes

Selecting a lane sets `aria-pressed`, updates `?session=`, and swaps the story. Lanes update **in place** as sessions advance, so a focused lane keeps focus.

**"Around it":** the tickets next to the sessions, so starting the next one is one click away:
- in review, linking to the desk
- takeable, with a secondary **Start an agent** (`start-agent-132`)
- blocked, with when it starts

### Story head
- **Kicker:** "/tdd · Claude Code · wt/noise-floor · issue #128".
- **Title:** the ticket name, linking to its card in the ticket graph.
- **State line:** "Building · started 09:05 · 41 min", "Waiting on you · paused at 09:18", or "Paused by you".
- **Controls:** a ghost **Open terminal** (`open-terminal`), and a secondary **Pause** / **Resume** (`pause-session`, `aria-pressed`). Pause is hidden while the session is waiting on you.

### Beats
The session as a list, grouped into **chapters** by acceptance criterion:
- **"Before any test · Orient":** claiming the ticket, reading the spec's decisions, noting prior work
- **"Criterion 2 of 4 · Chapters above −60 dB fail the check"**, and so on

Each beat has a time in mono, a **mark**, and one sentence:

| Beat | Mark | Example |
|---|---|---|
| Read | Small ring | "Read the ticket, then the spec's decisions on single-pass analysis…" |
| Note | Short dash | "The pass from *Extract the analysis pass* already runs astats, so…" |
| Red | Hatched square | "Wrote `flags the hiss fixture at -54 dB`. Fails: there is no noise floor check." |
| Green | Solid square | "Added the check beside loudness and peaks. 13 passing." |
| Refactor | Outlined square | "Moved the −60 dB limit into the shared ACX limits…" |
| Question | Diamond | "Paused to ask you before writing the test, because either answer changes what the test asserts." |
| You | Solid diamond, bold text | "You: …" (a note you sent) or "You answered: …" |

- **Test output:** red beats can carry it behind **Show test output**. It's collapsed by default and shown as mono pre-wrapped text.
- **Working row:** while the agent works, the last row is a spinning glyph with "Working" and a seconds counter. It says "Running the full worker suite" at the end.
- **Scrolling:** new beats arrive with a small rise. The pane follows new beats only if you're already near the bottom, so reading earlier beats never gets yanked away.

*Why beats and chapters instead of a terminal:* principle 2. Grouping by criterion shows *progress through the ticket's promises*, and the red → green → refactor rhythm shows whether `/tdd` is actually being followed. The raw output is one click away and never in the way.

### Question in the story
When the session is waiting on you, the composer hides and a **question card** appears inline under the beats: "Needs your answer to continue", the options, a note, and primary **Send answer and resume** (see [`../design/shell.md`](../design/shell.md#question-card-question-n)). After sending:
- the state line changes to "Building · resumed with your answer"
- the card is replaced by a "You answered" beat
- the composer returns, and focus moves to it

### Note composer (`nudge-composer`)
- **Field:** a one-line textarea, "Leave a note for this session. It reads it before its next step."
- **Send:** primary **Send note** (`send-note`), or Ctrl/Cmd + Enter.
- **Hint:** "Notes steer the agent without stopping it. Use Pause to stop it."
- **After sending:** a "You:" beat appears, followed shortly by the agent acknowledging it.

*Why notes, separate from pause:* the lightest steer should cost the agent nothing. A note is advice, and pause is a stop. The composer hint says so, so nobody pauses an agent when a nudge would do.

### Evidence rail (`session-evidence`)
- **Acceptance criteria · N of M:** the shared criteria list, updated live as criteria pass.
- **Test rhythm:** a strip of red and green marks, one per test run, in order, with "7 runs, red before every green · last green 09:36" and a small key.
- **Changes in wt/…:** each changed file in mono with "+38 −6" and a bar of additions and deletions. Deletions are hatched, so they read by shape.
- **Thread.**

*Why a test rhythm strip:* you can tell whether the agent is really doing test-driven development at a glance. Red then green, then red then green, looks like a regular pattern, and a run of greens with no reds stands out.

## Flows

- **Glance:** scan the lanes' latest beats and ticks → select the one that looks off → read its current chapter.
- **Nudge:** type a note → Send → the agent acknowledges and carries on.
- **Unblock:** a lane shows "Asked you: …" → select it → answer in the card → the session resumes.
- **Start the next one:** Around it → Start an agent → a new lane appears and takes focus.

## Why it looks this way

- **Three columns:** who (lanes), what's happening (story), and whether it's right (evidence). Each column answers a different question, so none has to do two jobs.
- **The primary is Send note:** the most frequent steer. Pause is secondary on purpose, because stopping an agent should take slightly more intent.
- **Marks by shape:** red and green tests are hatched and solid, never red and green (principle 7).

## Prototype shortcuts

- **Scripted sessions:** four sessions (#128, #129, #130, #132) with pre-written beats and a "live" queue revealed on a timer, about every 5s at random. The clock is faked from 09:46.
- **No-ops:** Open terminal only changes its label. Pause stops the scripted beats. Notes get a canned acknowledgement.
- **Criteria progress** updates from `crit` markers on the scripted beats.
- **Shared answers:** answering #130 here or on the desk uses the same `sessionStorage` key.
- **Not responsive:** no mobile layout; the three columns only narrow.

## Open questions

- **The session transport:** how beats, test results and questions stream from Claude Code, and how notes, pause and answers reach it (see [`../design/data-and-commands.md`](../design/data-and-commands.md)).
- **Classifying beats:** which tool calls become beats, how a "note" (an agent's reasoning) is distinguished from noise, and how a beat is tied to the criterion being worked on.
- **Sessions that end:** PR opened, failed, or abandoned. What the lane and story show, and where the lane goes.
- **Sessions from several efforts:** does live build show every effort's sessions, or only the current effort's (as prototyped)?
- **Where Open terminal goes:** a local terminal, the Claude Code app, or a web terminal.
- **Mobile:** probably lanes as a list and the story as its own view.
