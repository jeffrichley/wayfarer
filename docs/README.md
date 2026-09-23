---
type: playbook
status: draft
---
# Waystation: design writeups

Waystation is a companion app for the [mattpocock/skills](https://github.com/mattpocock/skills) workflow. It reads what `/wayfinder`, `/to-spec`, `/to-tickets`, `/tdd` and `/code-review` leave on GitHub. It shows that work moving, and it lets a person steer the agents doing it.

These docs record the **intent** behind the clickable prototype: what each screen is for, what each piece does, and why it looks the way it does. The prototype is the source of truth for how things look. These docs are the source of truth for why.

## The idea in one paragraph

Most tools in this space are boards: columns of cards that you drag around. Waystation is a **line** instead. Work moves along the skills in order (chart the way, write the spec, slice into tickets, build, review, land), and every screen shows where an effort is on that line. The skills already name things well, like the destination, fog, frontier, tracer bullet and seam, so the app uses those words and pictures rather than generic project-management ones. The goal the user set: *"not another board to look at. It should feel like it flows through the skills and is an extension of the skill system. Natural flowing, nothing to fight with. Not just a layer over git, but something that tells the story as it goes."*

## Decisions already locked

The user chose these when the project started. Treat them as fixed unless the user reopens them.

| Decision | Choice |
|---|---|
| First deliverable | A clickable prototype (done) |
| How much control the app has | **Watch and steer.** Waystation shows the work and can start, pause, answer, comment on and merge it. It is not a passive dashboard, and it doesn't replace Claude Code. |
| Where specs and tickets live | **GitHub Issues** |
| Views in scope | Wayfinder map, spec reader, ticket graph and frontier, live agent work, review and merge queue |
| Feel | Tell the story; follow the skills; calm; nothing to fight with |

## How to read these docs

1. **Always read first:** [`CONTEXT.md`](../CONTEXT.md), the glossary. Every doc uses its words exactly.
2. **Before building any screen:** [`design/principles.md`](design/principles.md), the rules that decide most layout and wording questions, plus the directions that were tried and rejected.
3. **For the screen you're building:** its writeup in `screens/`, plus the shared docs it points to:
   - [`design/visual-language.md`](design/visual-language.md): tokens, type, what colour means, the status glyphs, motion, dark mode, contrast.
   - [`design/shell.md`](design/shell.md): the top bar, route band, thread, and other pieces every screen shares.
   - [`design/data-and-commands.md`](design/data-and-commands.md): where each piece of data comes from on GitHub or in Claude Code, and what each steering action must actually do.

Each screen writeup has the same sections: **Intent**, **Layout**, **Pieces**, **Flows**, **Why it looks this way**, **Prototype shortcuts** and **Open questions**. The open questions are the fog: they are sharp enough to write down but not yet decided. Grill the user on them rather than guessing.

## Screens

| Screen | Prototype file | Station | Writeup |
|---|---|---|---|
| The line (home) | `index.html` | all | [`screens/the-line.md`](screens/the-line.md) |
| First run | `first-run.html` | `/wayfinder` | [`screens/first-run.md`](screens/first-run.md) |
| Wayfinder map | `wayfinder-map.html?effort=casting` / `acx` / `sample` | `/wayfinder` | [`screens/wayfinder-map.md`](screens/wayfinder-map.md) |
| Handoff to `/to-spec` | `wayfinder-map.html?effort=sample` | `/wayfinder` → `/to-spec` | [`screens/handoff-to-spec.md`](screens/handoff-to-spec.md) |
| Spec reader | `spec-reader.html` | `/to-spec` | [`screens/spec-reader.md`](screens/spec-reader.md) |
| Ticket graph | `ticket-graph.html` | `/to-tickets` | [`screens/ticket-graph.md`](screens/ticket-graph.md) |
| Live build | `live-build.html` | `/tdd` | [`screens/live-build.md`](screens/live-build.md) |
| Review desk | `review-desk.html` | `/code-review` → merge | [`screens/review-desk.md`](screens/review-desk.md) |

## The prototype

- **Paths:** the prototype is plain HTML. It lives in `prototype/`. `assets/wayfarer.css` holds the shared styles and `assets/wayfarer.js` holds the shared data and shell. Paths in these docs are relative to `prototype/`.
- **Finding pieces:** every region, control and repeated card carries a `data-piece` attribute. The writeups name pieces by that id, so searching for it finds the matching markup.
- **Sample content:** the sample repo is **Galley**, an audiobook editor for indie authors. It has four efforts at different stations:
  - *ACX compliance before delivery*: building
  - *Per-chapter voice casting*: still charting
  - *Choosing the retail sample*: one ticket from a clear way
  - *Manuscript upload states*: landed
  
  A second repo, **madrigal**, has nothing charted and drives the first-run screen. The ACX audio limits and retail sample rules are ACX's real published requirements. Every ticket, file, timestamp and conversation is invented.
- **"Now" in the sample** is Tuesday 15 September 2026, 09:46.
- **Frozen:** the prototype stores no demo state. Every screen opens at the same moment, and nothing a click does carries to another screen or survives a reload. A click on a ticket-changing action (merge, answer, start an agent, start grilling) gives its button's feedback and changes nothing else. The first-run chart and the retail sample's handoff still play through on their own page. The theme choice persists in `localStorage`.
- **Scripted sessions:** agent sessions, grilling conversations and `/to-spec` writing are scripted. Each writeup's **Prototype shortcuts** section says what is faked and what the real build needs.

## Suggested build order

This is a recommendation, not a decision:

1. **A read model of one repo's GitHub state:** maps, tickets, blocking edges, specs, PRs.
2. **The shell and the read-only screens built on it:** the line, the map, the spec reader, the ticket graph.
3. **Steering commands that only touch GitHub:** closing a ticket with a resolution, publishing tickets, merging.
4. **Commands that drive Claude Code sessions, and the screens that watch them:** live build, and the question and grilling panels on the desk.

Step 4 depends on an unresolved question: how Waystation talks to running sessions. See [`design/data-and-commands.md`](design/data-and-commands.md).
