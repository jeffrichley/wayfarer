# Wayfinder map

**Prototype:** `wayfinder-map.html?effort=casting` (still charting), `?effort=acx` (way clear, handed off), `?effort=sample` (one ticket left; see [`handoff-to-spec.md`](handoff-to-spec.md)) · **Station:** `/wayfinder` · **Arrive from:** the route band, home, the effort switcher, a Needs-you item · **Leave to:** the spec reader once handed off, the desk for grilling

## Intent

A `/wayfinder` map issue is markdown: a destination, a list of decisions, some fog, and child tickets with blocking links. This screen draws that as an actual **map**, so a person can see at a glance:
- how far the effort has come (the course walked from the start line)
- where the **frontier** is, and what's waiting on them there
- how much **fog** lies between the frontier and the **destination**
- what was ruled **out of scope**

It also lets them act on the frontier: start a grilling session, or close a ticket.

The side panel *is* the map issue's body, so nothing on the canvas is a second copy of the tracker.

## Layout

- **Top bar** (effort switcher) and **route band**, with `/wayfinder` current.
- **Canvas column** (`map-canvas`):
  - head: kicker "/wayfinder · map #147 · charted 9 Sep", the map title, and a glyph legend
  - the map canvas (1180 × 700, scaled to fit)
  - the **replay bar** (`replay`)
- **Side panel** (`map-drawer`): the map body, or one selected ticket.

## Pieces

### The canvas
Read left to right, like a chart:
- **Start line:** a vertical ink line on the left labelled "Charted" with the date. Tickets with no blockers connect straight to it.
- **Ticket nodes** (`map-ticket-<n>`): a glyph plus a label plate with the ticket's name (serif), its type and mode in mono ("GRILLING · HITL"), and a flag line when relevant ("Waiting on you", "Claimed by an agent", "Grilling with you").
  - **Placement:** in columns by how far down the dependency chain a ticket is.
  - **Selecting:** clicking selects the node (`aria-pressed`), highlights its edges, and opens it in the panel. Focus stays on the node.
- **Edges:**
  - start line → unblocked ticket
  - blocker → blocked ticket: **magenta once the blocker is decided** (the course walked), dashed while it's open
  - leaf ticket → destination: dotted, becoming magenta when the way is clear. Closed leaves only connect to the destination once the way is clear.
- **The fog band:** a stippled band between the last column of tickets and the destination, titled "Not yet specified". Each patch of fog is an italic serif note in the band, with a letter halo so it reads over the texture. When fog graduates, its note blurs out.
- **Destination** (`destination`): a ring with a dot and the destination sentence. When the way is clear it fills in and adds a line ("The way is clear. Handed to /to-spec").
- **Beyond the destination:** a tray to the right of the destination under a rule. Out-of-scope tickets **move there** with a slash glyph, so scope is drawn as place: they sit past where this effort ends.

### Legend
Decided, claimed, waiting on you, frontier, blocked, out of scope, not yet specified: each a glyph and a word.

### Replay bar (`replay`)
- **Controls:**
  - a play/pause button (`replay-play`)
  - a range slider over the map's history, with day ticks and "Now" at the end
  - **Back to now** (`replay-now`), shown only when you're in the past
- **Caption:** above the slider, one sentence for the current step, naming things in bold ("**What does ACX reject?** Six rules, all measurable. An agent claimed the fixture task.").
- **Scrubbing:** redraws the map as it was at that step. Nodes appear, get claimed, close and move out of scope; fog notes graduate; edges turn magenta.
- **Intro replay:** the first time a map opens in a browser session, it plays its own story quickly from charting to now (about 1.1s a step). Any click or key press outside the replay bar skips to now. It never plays under reduced motion, or when the URL selects a ticket.

*Why replay:* principle 2, tell the story. Watching fog clear and the course grow explains how the map got here better than reading its decisions list. It also makes it clear that the map is a living document.

### Side panel: the map body (nothing selected)
Its sections mirror the map issue:
- **Head:** "Map #147 · wayfinder:map" and the title.
- **Destination:** serif.
- **Notes:** the map's standing notes (domain, skills to consult).
- **Decisions so far · N:** each closed ticket's name, as a link that selects its node, with a one-line gist of the answer.
- **On the frontier · N:** claimed, waiting-on-you and frontier tickets, with their state and type.
- **Not yet specified · N:** fog notes in italic serif, or "No fog left between here and the destination."
- **Out of scope · N:** each ruled-out ticket with why.
- **Handed off:** on a handed-off map, "The way is clear. This map became *Pre-delivery compliance checks* #124", linking to the spec.
- **In the past:** a notice at the top ("Replaying 11 Sep. Return to now to act on the map.") and no actions.

### Side panel: one ticket (a node selected)
- **Head:**
  - **← Map** returns to the body and puts focus back on the node
  - chips for type, mode and issue number
  - the ticket name, and its state with the date it closed
- **Question:** the ticket's `## Question` body.
- **Resolution comment:** closed tickets only, in serif.
- **Why it is out of scope:** out-of-scope tickets only.
- **Claim:** claimed tickets; who has it and where findings land.
- **Graduated from fog:** tickets that came from fog, quoting the fog note they grew from.
- **Blocked by / Blocks:** the linked tickets with their glyphs. Selecting one moves focus to its node.
- **Actions, by state:**
  - **blocked:** "Reaches the frontier once *X* closes."
  - **claimed AFK:** when it started, and where the resolution will appear.
  - **HITL waiting on you** (casting's *What happens to chapters already rendered…*, `grilling-session`):
    - explains that it only resolves in a live exchange, and that the session runs `/grilling` and `/domain-modeling` as the Notes ask
    - primary **Start grilling session** (`start-grilling`)
    - starting it claims the ticket for you, turns its node to "Grilling with you", and opens a conversation with the agent's opening question, an answer box and **Send** (`grilling-send`)
    - each answer brings a sharper follow-up, and closing the session in Claude Code posts the resolution
  - **the last ticket on a map:** see [`handoff-to-spec.md`](handoff-to-spec.md).

## Flows

- **Orient:** read the canvas left to right. The magenta shows the ground covered, the fog shows how much is still unknown, and the diamond shows what's waiting on you.
- **Understand how it got here:** press play, or drag the slider.
- **Act on the frontier:** select the waiting ticket → Start grilling session → answer.
- **Follow a decision:** select a decided ticket → read its resolution → Blocks → jump to what it unblocked.

## Why it looks this way

- **Scope drawn as place:** the frontier sits at the edge of the known, fog sits before the destination (in scope but not sharp), and out-of-scope work sits past the destination. That's how the skill defines them (fog "only ever gathers toward the destination"), so the drawing *is* the definition.
- **Magenta only on walked edges:** the course. An open edge stays grey and dashed, so the eye follows the route actually taken.
- **The panel as the map body:** the skill says the map is an index, not a store. The canvas is a picture of the index, and the panel is the index itself, so the two can't disagree.
- **Label halos in the fog:** see the design history in [`../design/principles.md`](../design/principles.md). Clearings cut into the stipple caused ringing in dark mode.

## Prototype shortcuts

- **Hand-placed nodes:** every node has x/y coordinates, and out-of-scope nodes have a tray position.
- **Invented history:** the replay steps are sample events, each with a hand-written caption and the step at which each node was created, claimed, closed or ruled out.
- **Canned grilling:** the conversation has a fixed opener and follow-up whatever you type.
- **Demo state:** the "Start grilling session" state lives in `sessionStorage` and shows up on home and the desk too.
- **Three sample maps** live in one page's data, switched by `?effort=`. Selecting a ticket writes `#<n>` to the URL.

## Open questions

- **Automatic layout:**
  - columns from dependency depth
  - rows that keep related tickets together and edges uncrossed
  - fog notes placed in a band that fits their count
  - what happens past about 12 tickets or 6 fog notes
- **Fog graduation links:** the skill doesn't record which fog became which ticket (see [`../design/data-and-commands.md`](../design/data-and-commands.md)).
- **Replay events and captions:** where they come from.
- **Grilling in the panel vs in Claude Code:** whether the conversation happens here or in Claude Code, with the panel only mirroring it.
- **Several maps for one effort,** or re-charting after the destination is redrawn (the skill says out-of-scope work returns only as a fresh effort).
- **Mobile layout.**
