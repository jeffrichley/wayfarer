---
type: reference
---
# Ticket graph

**Prototype:** `ticket-graph.html` (9 tickets from spec #124) · **Station:** `/to-tickets` · **Arrive from:** the route band, the spec reader's traces, the thread, `#<n>` links · **Leave to:** live build (watch a session), the desk (answer or review), the spec

## Intent

`/to-tickets` slices a spec into **tracer-bullet** tickets, each declaring what blocks it. On GitHub that's a flat issue list with dependency links hidden in each issue. This screen draws the tickets as a **left-to-right graph of dependencies**, so a person can see:
- the order work *must* happen in
- the **frontier**: what can start right now
- what each ticket is waiting on, and what it will unblock
- how far each running ticket has got

From the frontier, they can start an agent.

## Layout

- **Top bar** and **route band**, with `/to-tickets` current.
- **Graph column** (`ticket-graph`):
  - head: kicker "/to-tickets · 9 tracer bullets from spec #124", title "Pre-delivery compliance checks, sliced", the reading instruction "Read left to right. A ticket reaches the frontier when every ticket feeding into it has landed.", and a **tally** of states ("2 landed · 1 in review · 2 building · 1 waiting on you · 1 takeable now · 2 blocked")
  - the canvas, sized by the layout and scaled (see [Layout](#layout-rules))
- **Detail panel** (`ticket-detail`), on the right: the selected ticket.

## Pieces

### Layout rules

Decided in [The ticket graph's automatic layout, and past 20 tickets](https://github.com/jeffrichley/wayfarer/issues/23). elkjs lays the graph out ([The stack](https://github.com/jeffrichley/wayfarer/issues/9)); these are the rules it is given.

- **The start line.** The first column is always a rail the full height of the graph. Before anything lands it is dashed and reads "Nothing landed yet · The course starts here". Every **Landed** ticket folds into it, and it then reads "N tickets landed" on the wash with a magenta edge: it is the course. Selecting it lists the landed tickets in the panel. Only Landed folds; a Landing ticket is still moving and keeps its card.
- **Columns count steps from now.** A ticket's column is how many tickets that have not landed stand between it and a session. The frontier is always the column beside the start line. In ELK this is layering strategy `LONGEST_PATH_SOURCE` over the tickets that have not landed: the default strategies push a ticket as *late* as it can go, which breaks the rule.
- **Rows are ELK's.** Crossing minimisation picks them. There are no streams: `/to-tickets` records only a title, blockers and a parent, and a stream derived from the edges alone runs across unrelated work.
- **Wires leave the start line level with the ticket they feed**, so the rail has no trunk and never moves.
- **Implied edges are hidden** by transitive reduction and listed in the panel under Blocked by.
- **Two card sizes.** A full card when a ticket is in flight (Building, Landing), waiting on you (Asked, Held), Takeable, or one step out (every open blocker is on the frontier or in flight). A name-only card, about half the height, further out. Nothing clips a name.
- **Motion.** When a ticket lands, its card slides into the start line, its dependents slide left, and name-only cards grow into full cards as they come within a step. Nothing else moves the layout.
- **Past 20 tickets** nothing else changes. The fold keeps the graph the size of the work left, and the canvas scrolls under the 0.7 scale floor rather than shrinking text below 11px.

The prototype that settled this is kept on the `prototype/ticket-graph-layout` branch.

### Cards (`ticket-card-<n>`)
- **Placement:** by the [layout rules](#layout-rules).
- **Size:** 184 wide. A full card is 128 tall; a name-only card is 56.
- **Card anatomy:**
  - **Top line** (mono, uppercase): glyph, state word, and the id on the right.
  - **Name:** serif, clamped to three lines.
  - **Foot:** the most useful fact for that state:

    | State | Foot |
    |---|---|
    | Landing | "In the merge queue" |
    | Building | "Working · 12 min" |
    | Asked | "Asked you a question" (in ink) |
    | Held | "Held · a blocking finding" (in ink) |
    | Takeable | "Nobody on it yet", or "Starts when a slot frees" at the cap |
    | Blocked | "Waiting on Flag noise floor" or "Waiting on 5 tickets" |

    Landed tickets have no card: they fold into the start line.

- **State styling, by shape and tone, never hue:**
  - landed: a washed background (finished, resting)
  - blocked: a dashed border on the page colour (not yet real)
  - takeable, Asked and Held: an ink border (ready to pick up, or waiting on you)
- **Selecting:** clicking a card sets `aria-pressed` and opens it in the panel. Focus stays on the card.
- **Trace:** a selected ticket lights what it waits on, back to the start line, and everything it frees; the rest dims. Clicking empty canvas or pressing Esc clears the selection and the trace.

### Wires
- **Shape:** orthogonal with rounded corners, from a blocker's right edge to the blocked card's left edge.
- **Met vs open:** **magenta** when the blocker has landed (the course walked), dashed grey while it's open. A ticket with no blockers hangs off the start line on a thin `--line` start-line wire.
- **Selection:** the selected card's wires turn hot (thicker) and are redrawn on top.
- **Implied edges** are not drawn. *Flag noise floor* → *Block ACX export* is already implied through *Check room tone*, so it's drawn only once, through room tone. The panel still lists it under Blocked by, marked "implied through Check room tone".
- **Gate note:** beside the last card, "Every check feeds the export gate. It is the last ticket to reach the frontier."

### Detail panel (`ticket-detail`)
- **Head:** chips (Issue #, `ready-for-agent`, and Prefactor when it is one), the ticket name, and its state with context ("Building · 3 of 4 criteria").
- **Action block, by state:**

  | State | Block |
  |---|---|
  | Takeable (`start-agent-block`) | "On the frontier". A setup list: Agent *Claude Code*, Skill */tdd*, Worktree *wt/books-status from main*. Primary **Start an agent on this ticket** (`start-agent`). |
  | Building | "In a session": what it's doing, and a secondary **Watch the session** (`watch-session`) |
  | Waiting on you | "Paused for you": the question quoted, and a secondary **Answer on the desk** (`answer-question`) |
  | In review | "Waiting on review": the review verdict, and a secondary **Review PR #141** (`review-pr`) |
  | Blocked | "Not yet": "Reaches the frontier once *X* and *Y* land.", and a ghost toggle **Queue an agent for when it unblocks** (`queue-agent`, `aria-pressed`) |

- **What to build:** the ticket's end-to-end behaviour, in plain language.
- **Acceptance criteria · N of M:** the shared criteria list, with test names.
- **Blocked by / Unblocks:** linked tickets with glyphs. Following one selects its card and moves focus there.
- **Thread:** map → spec → ticket → session → PR → landed (see [`../design/shell.md`](../design/shell.md#thread)).

**Start an agent:**
- The button becomes a disabled "Agent started in wt/books-status", and a ghost **Watch it work** link appears beside it.
- The card, tally, top bar and route band update *around* the clicked button without rebuilding it, so focus stays put.

## Flows

- **What can start now?** Look for bold-bordered cards → select one → read What to build and its criteria → Start an agent.
- **Why is the export gate still blocked?** Select it → Blocked by lists five tickets and their states → queue an agent so it starts when they land.
- **Where does this ticket come from?** Thread → the spec story → the map decision.

## Why it looks this way

- **Columns by when a ticket can start, counted from now:** reading left to right *is* the build order, so a person never has to work out a topological sort in their head. Counting from now keeps the frontier beside the start line at every size.
- **Done work folds into the start line:** the graph is the size of the work left, not the work done, and the course stays drawn as the one magenta thing on the left.
- **The foot changes by state:** each card surfaces the one fact that matters for its state, and a card never carries every field at once.
- **Magenta wires only where a blocker landed:** the course, again. The landed part of the graph reads as a route already travelled.
- **"Queue an agent" is a ghost toggle, not a primary:** the only primary on this screen belongs to starting work that can start *now*.

## Prototype shortcuts

- **Hand-placed layout:** card positions (`POS`) and wire routes (`WIRES`) are hand-placed, including which implied edges to skip.
- **Default selection:** *Show compliance status on My Books* (#132) is selected by default, because it's the takeable one.
- **Demo state:** "Start an agent" and "Queue" are saved in `sessionStorage`. Starting #132 makes it appear as a lane in live build.

## Open questions

- **Several specs at once** in one effort's graph.
- **Where "Queue an agent" lives,** and what it does if the blocker is abandoned.
- **Starting an agent with other settings** (another skill, model or base branch): is the setup list editable?
- **Tickets from more than one spec:** separate graphs, or one graph grouped by spec?
- **Mobile layout.**
