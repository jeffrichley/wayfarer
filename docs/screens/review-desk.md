---
type: reference
status: draft
---
# Review desk

**Prototype:** `review-desk.html?item=<key>` (`pr-141`, `q-130`, `map-160`, `g-152`) · **Station:** `/code-review` → merge · **Arrive from:** "Needs you" in the top bar, Needs you on home, action blocks in the ticket graph · **Leave to:** the ticket, the session, the map

## Intent

Everything waiting on a person, in one place, ordered so their attention goes where it frees the most work. Each kind of item gets a working surface built for *that* decision, not a generic detail page:
- **a PR:** judge it against the spec, not just the code
- **a question:** answer it with the spec's relevant decisions beside it
- **a grilling ticket:** hold the conversation
- **a map about to clear:** jump to where the decision is made

It answers: *what needs me, what happens when I decide, and what should I know before I do?*

## Layout

- **Top bar** and **route band**, with the `/code-review` station current in the prototype.
- **Queue** (`needs-you-queue`), left, 350px: "Needs you", "What holds up the most work, first."
- **Item** (`desk-item`), right: a scrolling working surface (`m-pane`) and, for PRs, a pinned **merge bar** at the bottom.

## Pieces

### Queue (`desk-<key>`)
- **Order:** one list across efforts, by what each item holds up ([ordering rules](../design/data-and-commands.md#needs-you-derived)). Each item names its effort. The order freezes while you are on the desk and re-ranks when you come back; new items join at the bottom, marked new.
- **Each item** is a button showing:
  - a glyph: half ring for a review, diamond for anything waiting on an answer
  - the kind in mono ("Review", "Question", "Grilling · HITL", "Seam · /to-spec")
  - the name in serif
  - the ask ("/code-review found one gap against the spec")
  - what it holds up ("Holds up 4 tickets · 1 starts the moment it lands")
- **Resolved items stay in place,** dimmed, with what happened ("Merged just now", "Answered · the session resumed"), so the person sees their own progress through the queue.
- **Selecting** sets `aria-pressed` and `?item=`, and the queue repaints in place so focus stays on the item.

### PR review (`pr-141`)
**Head** (`pr-header`):
- kicker "/code-review · PR #141 · wt/peak-ceiling → main"
- the ticket name, linking to its card
- facts: state, "+45 −1 · 4 files", CI passed, "Delivers stories 3 and 4"

**The two axes, side by side** (`code-review-axes`): the two parallel reviews `/code-review` runs.
- **Standards** (filled glyph, "No findings"): a sentence on why, naming the ticket whose pattern it follows and the seam the tests go through.
- **Spec** (half glyph, "1 finding"): a **finding card** (`spec-finding`) with:
  - the story and criterion
  - the criterion quoted in serif
  - what's wrong in plain words ("It would still pass if every peak were reported at 0:00.")
  - a suggestion
  - a secondary **Send to the agent** (`send-finding`) and a ghost **Show in diff**

*Why two axes and not one list of comments:* this is how `/code-review` works, and it separates "is the code good?" from "does it do what we agreed?" The second question is the one a person is uniquely placed to answer.

**Acceptance criteria, proven by tests** (`criteria-tests`): a table with each criterion, its test name in mono, and the result. A weak one says "Passes, weakly asserted" in ink with a half checkbox.

*Why:* review starts from the promise, not the diff. A criterion that passes weakly is the most common way an agent satisfies the letter of a ticket but not its intent.

**Changes** (`pr-diff`):
- **File tabs:** each tab shows the file name and +/− counts.
- **Diff table:** old and new line numbers, a sign cell (solid for added, outlined for removed), and code. Removed code is struck through.
- **Inline finding:** the `/code-review` finding sits under its line.
- **Commenting:** click or press Enter on any line to open a comment box, "Comment for the agent". **Send to agent** posts it, and the comment goes to the worktree session, not just GitHub.

**Merge bar** (`merge-bar`):
- **Consequence sentence:** "Merging lands *Flag peaks above −3 dB*. *Block ACX export while any chapter fails a check* will still wait on 4 tickets."
- **Actions:**
  - secondary **Request changes** (`request-changes`) reveals "What should the agent change before this can merge?" and **Send changes request**
  - primary **Approve and merge** (`approve-merge`)
- **After merging:** the sentence becomes "*…* landed. 3 of 9 tickets are in." The queue item, top bar and route band update.

### Question (`q-130`)
- **Head** (`question-header`): "/tdd · Claude Code · wt/credits · paused 09:18", the ticket, facts ("Waiting on you", "2 of 3 criteria passing", "Unblocks *Block ACX export*").
- **Left:** the **question card**: the options with their consequences, a note, and **Send answer and resume**. Once answered, it becomes the conversation, with "Posted to #130. *Watch the session resume*".
- **Right: What the spec already says:** the implementation decision and the story that bear on the question, quoted with their sources (the decision links to its map ticket), then "Criteria so far".

*Why the spec beside the question:* the agent asked because the spec doesn't settle it. Showing exactly what the spec *does* say keeps the answer consistent with earlier decisions.

### Grilling ticket (`g-152`)
- **Head** (`grilling-header`): the map, the issue and the ticket name, with Grilling and HITL chips and its state.
- **Left** (`grilling-panel`): why it needs a live exchange, and primary **Start grilling session** (`start-grilling`). Starting shows the conversation and an answer box with **Send** (`grilling-send`).
- **Right:**
  - "Answering this unblocks" (the blocked tickets)
  - "And clears the way toward" (the fog note it will clarify)
  - "Decided so far on this map"

### Map about to clear (`map-160`)
- **Head** (`sample-header`): follows the handoff stages. First the last ticket, "Claimed by you · in session since 09:32", then "The way is clear" with "Handing off to /to-spec · the seam waits on you".
- **Panel** (`sample-panel`): a sentence on the stage, and primary **Check the resolution on the map** or **Agree the seam on the map** (`open-sample-map`). There's no action once the spec is written.
- **Right:** the map's destination.

*Why this item links out instead of acting here:* the moment belongs on the map (see [`handoff-to-spec.md`](handoff-to-spec.md)). The desk keeps it in the queue so it's never missed.

## Flows

- **Review a PR:** read the axes → open the finding → Show in diff → comment on a line or Send to the agent → Request changes, *or* Approve and merge.
- **Answer a question:** read the question → check what the spec says → pick an option, add a note → Send answer and resume → the item resolves in place.
- **Work down the queue:** top to bottom. Resolved items stay put and dim, so your place in the list never jumps.

## Why it looks this way

- **The queue never reorders under you:** resolving an item marks it done in place, instead of removing it and shifting the list.
- **One primary per item:** Approve and merge, Send answer and resume, Start grilling session, or the map link. Everything else is secondary or ghost.
- **Consequences stated before the button:** the merge bar's sentence is principle 5.
- **Diffs read without colour:** additions and deletions are shown by sign-cell shape and strikethrough.

## Prototype shortcuts

- **Hard-coded items:** four items with hand-written content, and the diff is a small fixed excerpt.
- **Queue order is authored,** not computed. The real rule is in [`data-and-commands.md`](../design/data-and-commands.md#needs-you-derived).
- **No demo state:** merge, answer, send finding and start grilling change their own controls and nothing else. The queue never resolves, and home, the ticket graph and live build don't see them.
- **Local-only comments:** line comments and change requests change only local markup.
- **Station highlight:** the route band always highlights `/code-review`, even for question and grilling items.

## Open questions

- **Scaling the diff:** large PRs (many files, long diffs), and whether the diff hides files the finding doesn't touch.
- **Where findings and line comments are stored** (PR review comments?) and how they reach the session (see [`../design/data-and-commands.md`](../design/data-and-commands.md)).
- **Items for `/to-tickets` drafts:** these belong in the queue. Should they get a desk surface or link to the spec reader?
- **Merge rules:** required approvals, branch protection, failing CI. How the merge bar explains why it can't merge.
- **Team use:** who "you" is when several people share the desk; assignment and claiming.
- **The route band on the desk:** it spans several efforts and stations. Should it follow the selected item's effort?
