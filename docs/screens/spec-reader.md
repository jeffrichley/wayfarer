---
type: reference
status: draft
---
# Spec reader

**Prototype:** `spec-reader.html` (spec #124, *Pre-delivery compliance checks*) · **Station:** `/to-spec` · **Arrive from:** the route band, the thread, a map that has handed off · **Leave to:** the map a decision came from, the ticket graph, a specific ticket

## Intent

A spec from `/to-spec` is a long GitHub issue: problem, solution, a *long* list of user stories, then decisions. On GitHub it reads as a wall of text with no sign of which parts are built. This screen turns it into a **readable document that knows its own coverage**. It shows:
- which ticket delivers each user story, and how far along that ticket is
- where each decision came from on the map
- which stories no ticket covers yet, with a way to fix that

It answers: *is everything this spec promises actually on its way?*

## Layout

- **Top bar** and **route band**, with `/to-spec` current.
- **Outline** (`spec-outline`), a left column:
  - "Spec #124"
  - the template sections with item counts; the section in view is highlighted
  - **Seam agreed with you**: the seam in a sentence
- **Document** (`spec-document`), a centred reading column about 650px wide, with a margin column about 290px wide beside every item for **traces**.

## Pieces

### Header (`spec-header`)
- **Title block:**
  - kicker "/to-spec · issue #124 · ready-for-agent"
  - the spec title as a large serif headline
  - byline: "Written from the map *ACX compliance before delivery* and its seven decisions. Published 12 Sep; sliced into nine tickets on 14 Sep."
- **Story coverage** (`story-coverage`), in the margin:
  - a figure, "14 of 16 stories have a ticket"
  - a **16-cell bar**, one cell per story: solid means delivered (every delivering ticket landed); half-filled means being built or reviewed; hollow means waiting to start; dashed means no ticket
  - a key with counts, where "2 without a ticket" jumps to the first uncovered story

*Why a bar of stories rather than a percentage:* each cell is a real story, in order, so the gaps have a position. "Stories 14 and 16" is actionable, and "87%" isn't.

### Sections
These follow the `/to-spec` template exactly, so the reader matches the issue: Problem statement (`spec-problem`), Solution (`spec-solution`), User stories (`spec-stories`), Implementation decisions (`spec-implementation`), Testing decisions (`spec-testing`), Out of scope (`spec-out-of-scope`), Further notes (`spec-notes`). Headings are serif, and prose is set large (16px, 1.7 line height) for reading.

Each numbered item is a row: its number in mono, its text, and a **trace** in the margin. The margin column has a heading per section:

| Section | Margin heading | Trace shows |
|---|---|---|
| User stories | Delivered by | Each ticket that delivers the story: glyph, name link, id, and state word ("Building"). An uncovered story shows a dashed glyph and **No ticket delivers this yet** in ink. |
| Implementation decisions | Decided on the map | The map decision ticket it came from (link to that node), or a note such as "Agreed during /to-spec, when the seams were checked with you" |
| Testing decisions | Came from | The map ticket (for example the fixtures task), or a note such as "The one seam agreed during /to-spec" or "Found while exploring the repo" |
| Out of scope | Ruled out | The out-of-scope map ticket, or a note ("A separate effort, not yet charted") |

**Linked highlighting:** hovering or focusing a ticket link in any trace highlights *every* story that ticket delivers, with a wash and an ink bar at the left edge. That shows a ticket's full footprint without leaving the page.

### Slice the uncovered stories (`slice-uncovered`, `draft-tickets`, `publish-drafts`)
- **Toggle:** under the user stories, a secondary **Slice the 2 uncovered stories** ("Runs /to-tickets on stories 14 and 16 only.") opens a **draft panel**.
- **Draft panel:**
  - "Drafted by /to-tickets · not published", with the reminder "Check the granularity and blocking edges before publishing."
  - each drafted ticket's title, which story it delivers, and its blocking edges, with the reason ("Blocked by nothing: the compliance read model already exists")
  - primary **Publish 2 tickets** ("Labels them ready-for-agent on GitHub.")
- **After publishing:**
  - the two stories' traces show the new tickets as "Published just now · takeable"
  - the coverage figure and bar update to 16 of 16
  - the button reads "Published as #144 and #145"

*Why the drafts stop for a check:* `/to-tickets` quizzes the user on granularity and blocking before publishing. The draft panel is that quiz.

### Outline behaviour
- Clicking a section scrolls the document smoothly and updates the URL hash.
- The active section follows scroll position.
- Loading with a hash scrolls to that section or story.

## Flows

- **"Is this spec covered?"** Read the coverage figure → click "2 without a ticket" → read the uncovered story → Slice → check the drafts → Publish.
- **"Why did we decide this?"** An implementation decision → its map ticket → read the resolution on the map.
- **"What is this ticket actually for?"** Hover the ticket link → every story it delivers lights up.

## Why it looks this way

- **Document first:** a spec is read, so the reading column gets editorial type and generous spacing, and the tracker metadata moves to the margin.
- **Margin traces rather than inline badges:** the text stays readable, and the traces line up in one column you can scan down.
- **Accent budget:** the only accent use is the draft panel's primary, which appears only while drafts are open. The page's normal state has no primary at all, because reading is the job.

## Prototype shortcuts

- **Hard-coded content:** the stories, decisions and notes are fixed in the page. The story → ticket mapping comes from each sample ticket's `stories` list.
- **Draft tickets are fixed**, and publishing isn't saved in `sessionStorage`, so it resets on reload.
- **One spec only:** the page renders spec #124. The retail sample spec (#168) from the handoff has no page.
- **Below 920px:** the outline hides and traces move under their items.

## Open questions

- Parsing: how a spec's markdown maps to sections and numbered items when authors deviate from the template.
- The **story → ticket** and **decision → map ticket** links (see [`../design/data-and-commands.md`](../design/data-and-commands.md)).
- Editing: is the spec read-only here, with edits made on GitHub?
- When a spec is re-published or edited after slicing, how coverage handles stories that were renumbered.
- Specs that didn't come from a map (a `/to-spec` run straight from a conversation): the byline and "Decided on the map" traces need a fallback.
