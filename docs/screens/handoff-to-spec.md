---
type: reference
status: draft
---
# The way is clear: handoff to `/to-spec`

**Prototype:** `wayfinder-map.html?effort=sample` (the map *Choosing the retail sample*) · **Station:** `/wayfinder` → `/to-spec` · **Arrive from:** its row on home, the effort switcher, the desk item `map-160`, the Needs-you item "In session with you" · **Leave to:** slicing into tickets

This is a moment on the [Wayfinder map](wayfinder-map.md), not a separate screen. Read that writeup first; this one covers only what's different.

## Intent

The end of wayfinding is the most satisfying event in the workflow: the last decision lands, the fog is gone, and the way to the destination is visible. The skill defines this moment as "no tickets remain and no fog" and says the pull to start doing the work is the signal to hand off.

This moment should:
1. **Make the arrival felt:** the fog lifts, the course reaches the destination, and the skill line moves on.
2. **Carry the effort straight into `/to-spec`** without losing the map's context.
3. **Keep the person's two real decisions in their hands:** the last resolution, and the seam.

## The sample state

*Choosing the retail sample* (map #160) has:
- 5 decided tickets
- 1 ruled out of scope ("Generate a narrated trailer with music")
- 1 open ticket, *Does the sample follow later edits to its chapter?* (#166), claimed by you and in a grilling session since 09:32
- 1 patch of fog: "Whether a changed sample needs its checks run again. Hangs on whether samples follow edits."

The route band shows `/wayfinder` active ("5 decided · 1 in session") and `/to-spec` pending ("After the way is clear").

## Stage 1: one decision from a clear way

### Map body panel (`last-call`)
A block at the top of the map body, titled **One decision from a clear way**: "Everything else on this map is decided or ruled out, and the last patch of fog hangs on one ticket. Closing it clears the way." Below that is the ticket as a link, with "In session with you · Grilling, HITL".

### The last ticket's panel
Selecting #166 shows the normal ticket head ("Claimed by you · in session since 09:32") and its Question, then:
- **Grilling session · with you** (`last-ticket-session`): the conversation so far, mirrored from the session. The agent asks, you answer, the agent sharpens, you decide. The last message says it's sharp enough to close, *and* that the answer leaves the fog with nothing to decide.
- **Resolution comment** (`resolution-comment`):
  - a serif textarea holding the resolution **drafted from your answers**, editable before it posts
  - **Closing this ticket**, a list of consequences shown before the click:
    - filled glyph: posts the resolution and adds it to Decisions so far
    - fog mark: clears the last patch of fog *without a new ticket*, quoting the fog note
    - destination mark: leaves nothing open between here and the destination
  - primary **Post resolution and close** (`close-last-ticket`). An empty resolution is refused with "The resolution can't be empty."

*Why show the consequences before the click:* principle 5. This close ends the map. The person should know it's the last one, and that fog can dissolve into no ticket at all, which the skill allows ("one patch may graduate into several tickets, or none").

## Stage 2: the way becomes clear

This plays once, on the click. Timings are approximate, and all of it collapses to an instant under reduced motion.

| t | What happens | Where |
|---|---|---|
| 0 | The node settles into a filled glyph with a small scale pulse. The map body replaces the ticket panel, and focus moves to its new heading. | Canvas, panel |
| 0.15s | **The fog drifts off the chart:** the band slides right and fades over about 2.5s. The fog title fades, and the last fog note blurs away. | Canvas |
| 0.9s | **The course draws into the destination:** each leaf's edge to the destination draws itself in magenta, staggered | Canvas |
| 0.9–1.65s | The panel's blocks rise in, staggered | Panel |
| 1.9s | **The destination fills,** and a single magenta ring pulses out from it. Its line reads "The way is clear. Next: /to-spec." | Canvas |
| 1.9s | **The skill line moves on:** the track from *Chart the way* to *Write the spec* draws in magenta. `/wayfinder` reads "6 decisions · way clear", and `/to-spec` turns to a diamond, "Agree the seam". | Route band |

The replay bar gains a new "now" event: "The sample stays as chosen. The last patch of fog cleared without a new ticket. **The way is clear.**"

*Why this choreography:* every movement is something the skill says has just happened: fog cleared, route to the destination visible, effort moved to the next station. It's the product's biggest flourish, and it's earned because it happens once per map.

## Stage 3: the handoff panel (`handoff-to-spec`)

The map body becomes the handoff:
- **Head:** "Map #160 · wayfinder:map", the heading **The way is clear**, and a lead: every ticket is decided or ruled out and no fog is left. The destination is a spec, so the course continues at `/to-spec`.
- **Hand off to /to-spec:** the three steps of `/to-spec`, drawn as a thread:
  1. **Read the map and its decisions** (done): "6 decisions, 1 ruled out, and CONTEXT.md. /to-spec writes from what's decided and doesn't interview you."
  2. **Agree the seam** (with you; diamond) (`seam-proposal`):
     - the proposal from `/to-spec`, in serif: *test through the compliance read model that Pre-delivery compliance checks already built*
     - two radio cards: **Use the compliance read model** (existing seam, preselected, because `/to-spec` prefers existing seams) and **Give samples their own seam** (two seams to test through)
     - an optional "Anything the spec should know" note
     - primary **Agree seam and write the spec** (`agree-seam`)
  3. **Write and publish the spec** (pending): which template sections it will write, labelled `ready-for-agent`.
- **Destination:** serif.
- **Written from these decisions · 7** (`spec-sources`): every decided and ruled-out ticket, each linking to its node, tagged with the spec section it feeds ("→ Implementation decisions", "→ Out of scope").

*Why the seam is the one question:* `/to-spec` does not interview. The skill's only human check is on seams ("Check with the user that these seams match their expectations"). Waystation shows exactly that question, with the recommended answer preselected and its trade-off stated.

*Why "Written from these decisions":* provenance (principle 10). It shows the person, before writing, what the spec will be made of, and it's the same traceability the spec reader shows afterwards.

## Stage 4: writing and publishing

- **On Agree seam:** the button becomes a disabled "Seam agreed" and keeps focus. The seam step fills, and **Write and publish** starts spinning.
- **Writing:** the template sections tick off one at a time, with their item counts: Problem statement, Solution, User stories 12, Implementation decisions 4, Testing decisions 3, Out of scope 1, Further notes.
- **Published:**
  - the step fills and reads "Published as *Retail sample suggestions* #168, labelled ready-for-agent. The map is closed with a pointer to it."
  - a **spec card** (`spec-168`) appears: the issue kicker, title, a two-sentence problem and solution summary, and counts
  - the head's kicker changes to "Map #160 · closed"
  - the destination line becomes "Written up as Retail sample suggestions."
  - the `/to-spec` track draws on to *Slice into tickets*, which shows a bold ring: "Ready to slice"
  - a new replay event reads "Handed to /to-spec as **Retail sample suggestions**. The map is closed."
- **Next:** primary **Slice into tickets** (`slice-into-tickets`), "Runs /to-tickets. You check the drafts before they publish." Clicking it turns it into a disabled "Slicing into tickets", and the route band shows `/to-tickets` building.

## Everywhere else

- **Home:** the effort's row follows the stages (one in session → way clear with "Agree the seam" bold → spec written with "Ready to slice" → slicing). The chronicle gains "now" entries, and the standfirst changes.
- **Needs you:** the item changes from "In session with you · Clears the way" to "Seam · Unblocks the spec", then leaves once the spec is written.
- **The desk** (`map-160`): explains the stage and links to the map ("Check the resolution on the map" / "Agree the seam on the map").
- **Effort switcher:** the meta follows the stages.

## Prototype shortcuts

- **Scripted content:** the conversation, the drafted resolution, the seam proposal, section counts, spec number #168 and the spec summary are all fixed. Choosing "own seam" only changes the recorded wording.
- **Writing time:** "writing" is a timer, about 320ms per section.
- **Storage:** stage state is `sessionStorage` keys `sample.closed` (the resolution text), `sample.seam`, `sample.written` and `sample.sliced`.
- **No spec reader for this spec:** `spec-reader.html` only renders the ACX spec, so the spec card doesn't link anywhere.

## Open questions

- **Destination kinds:** what the handoff shows when the destination is a *decision* (nothing to write, so the map just closes) or a *change made in place* (straight to `/tdd` or `/to-tickets`?).
- **Where the drafted resolution comes from:** the grilling session writes it, but how does it reach the panel, and is editing it here allowed to diverge from the conversation?
- **Several seams:** if `/to-spec` proposes more than one, is it a list of agree/adjust rows?
- **Declining the seam:** what happens when the person rejects both options and writes their own? Does `/to-spec` respond in a conversation before writing?
- **Writing progress:** whether it's real progress from the session, or an indeterminate "writing" with the result arriving at the end.
- **The map → spec pointer** (see [`../design/data-and-commands.md`](../design/data-and-commands.md)).
- **Handoff by another session:** if someone closes the last ticket in Claude Code rather than here, the moment should still play the next time the map is opened. *Proposed:* play it once per person, the first time they see the map clear.
