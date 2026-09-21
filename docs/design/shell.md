---
type: reference
status: draft
---
# The shell and shared pieces

These are the pieces more than one screen uses. In the prototype they're built by `assets/waystation.js` and styled in `assets/waystation.css`. Each screen calls `WS.renderTopbar` and, except home, `WS.renderRoute`.

## Frame

Every screen is a full-height grid: the **top bar**, the **route band** (every screen except home), then the screen's own content. Content regions scroll on their own (`.pane`), so the top bar and route band stay in view. A screen's content is usually a canvas or document beside a side panel (`.split` with `.side` / `.side-l`).

## Top bar (`topbar`)

It answers: where am I, is anything working, and does anything need me?

| Piece | `data-od-id` | What it does |
|---|---|---|
| Wordmark | — | "Waystation" with a mark: a filled dot, a line, and an open ring. That's a small course from a landed point to the next station. It links home. |
| Repo switcher | `repo-switcher` | Mono repo name with a menu. Each repo shows a one-line state ("3 efforts on the line", "Connected today · no maps yet"). A repo with no maps opens first run. |
| Effort switcher | `effort-switcher` | Appears on effort screens: the effort's name in serif with a menu of efforts. Each row has a status glyph and a sentence ("Building · 2 of 9 landed · 2 building"). It links to wherever that effort currently is. |
| Agents working | `agents-working` | A spinning glyph and a count of running sessions across the repo. It links to live build. |
| Needs you | `needs-you` | A count of everything waiting on a person. It links to the desk. The count badge is ink, not accent. When nothing is waiting it becomes a quiet grey badge with a 0, and stays in place. |
| Theme toggle | `theme-toggle` | Switches between the chart and the night chart. See [`visual-language.md`](visual-language.md#themes). |

**Menus:** open on click. Escape and an outside click close them. Only one menu is open at a time, and after Escape focus returns to its button.

**Below 920px:** the crumbs hide, the effort name truncates with an ellipsis, and the repo switcher stays visible only when there's no effort crumb.

## Route band (`route`): the skill line

This is the spine of the product. It shows six **stations** in a row, and each station shows:

1. the **skill** in mono (`/wayfinder`)
2. a **node** glyph for the station's state, with a **track** leading to the next station
3. the station **name** in serif ("Chart the way")
4. an **output line** summarising what's there ("9 tickets · 1 takeable", "1 PR waiting on you")

| Station | Skill | Links to |
|---|---|---|
| Chart the way | `/wayfinder` | The effort's map |
| Write the spec | `/to-spec` | Spec reader |
| Slice into tickets | `/to-tickets` | Ticket graph |
| Build | `/tdd` | Live build |
| Review | `/code-review` | Review desk |
| Landed | merge | — (the end of the line; shows a dot per ticket, filled when landed) |

**Node states:**
- done: `st-done`
- active: the glyph of the most urgent thing there. A question beats building, which beats idle.
- next move: `st-take`
- not reached: `st-pending`
- skill missing (first run only): `st-blocked`
- Landed is shown as a flag.

**Tracks:** a track is **magenta and solid** when the course has reached the next station, and **dashed** when it hasn't. That's the course, drawn in the accent.

**The current page's station:** its name is bold and underlined with ink.

**Stations with no screen yet** (for example, an effort still charting has no spec) render as disabled, not as links. The title explains why ("Opens once the map's way is clear").

**First-run mode** replaces each output line with **readiness**: "Installed", "Not installed" or "GitHub · main". The station glyphs then mean installed (thin ring) or missing (dashed). See [`../screens/first-run.md`](../screens/first-run.md).

**Handoff:** when the course moves to a new station, that station's track draws in once (`WS.drawTrack`).

*Why a band on every screen:* it's the navigation and the progress indicator in one. Moving between screens *is* moving along the line, so nobody needs a separate tab bar or breadcrumb.

## Thread

A vertical list tracing one ticket from map to merge. It appears in the ticket graph's panel and live build's evidence rail. There are six steps, each with a glyph, the skill in mono, a linked name, and a one-line meta:

1. `/wayfinder`: the map, with the decisions this ticket relies on, by name
2. `/to-spec`: the spec, with the stories this ticket delivers
3. `/to-tickets`: the ticket, and what it waits on
4. `/tdd`: its worktree session, or "No session yet"
5. `/code-review`: its PR and the review verdict
6. merge: landed, and when

The connecting line is solid through done steps and dashed into pending ones.

*Why:* this is principle 10, provenance. From any ticket you can get back to *why* it exists and forward to *where* it's going.

## Acceptance criteria list

A list of the ticket's criteria, each with a checkbox mark (not met / met / weakly met) and, beneath it, the name of the test that proves it in mono. It's used in the ticket graph, live build, the review desk question view and the PR view. A criterion's test name is the bridge between the spec's words and the code.

## Question card (`question-<n>`)

The shape of a session paused to ask something:
- the agent's message: worktree, time and the question
- two to four answer options as radio cards, each with a sentence on its consequence
- an optional note ("Anything the agent should know")
- a primary action: "Send answer and resume"

It's used inline in live build and on the desk. Rules:
- Sending requires an option or a note.
- After sending, the controls lock and the hint says where the answer was posted ("Posted to #130. The session resumes.").

## Conversation (`.convo`)

Messages marked `AI` or `You`, with a mono "by" line naming the skill and time. It's used for grilling sessions, questions and answered history. Your messages have an ink avatar.

## Canvas fitting (`WS.fitCanvas`)

Charts are drawn on a fixed-size stage and scaled to their column. There's a minimum scale (about 0.7), so text never gets unreadably small; below it, the viewport scrolls. A ResizeObserver refits on resize.

## Demo state (prototype only)

`WS.mark`, `WS.has` and `WS.got` store demo actions in `sessionStorage` (`waystation.demo.v1`). `WS.ticket(n)` applies those actions to the static sample tickets to derive live state, for example merged → landed, or answered → building. The real build replaces all of this with the read model described in [`data-and-commands.md`](data-and-commands.md).
