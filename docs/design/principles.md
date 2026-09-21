---
type: principles
---

# Principles

These rules decided most of the prototype. When a design question comes up during the build, the answer is usually here. Words in **bold** are defined in [`../../CONTEXT.md`](../../CONTEXT.md).

## 1. A line, not a board

Work moves along the **skill line** in one direction, and the UI shows where it has got to. The route band across the top of every effort screen *is* the navigation: each **station** links to the screen for that skill. Home shows every effort as a row across the same six stations.

*Why:* the user asked for something that "flows through the skills" and is "not another board to look at." A board invites dragging cards between columns, but in this workflow a ticket moves because a skill ran, not because someone dragged it. A line fits how the work actually moves.

*In practice:* take a new view's layout from its station's skill. The spec reader follows the `/to-spec` template section by section. The map follows the `/wayfinder` map body. The ticket graph reads left to right in dependency order.

## 2. Tell the story

Every screen answers "what happened, and what happens next?" in sentences.
- Home opens with a headline about what changed since your last visit.
- The chronicle is written in prose.
- A session is shown as **beats** grouped under the criterion being worked on, not as terminal output.
- A map can **replay** its own history.

*Why:* the user wanted "something to tell the story as it goes", more than a layer over git. Sentences also carry the reason a thing happened, which a status label can't.

*In practice:* write UI copy as short, complete sentences that name things ("*Flag peaks above −3 dB* finished its session and opened PR #141"). Use numbers to support a sentence, not in place of it.

## 3. Refer by name

Tickets, maps and specs are called by their titles everywhere. The id rides small and in mono after the name (`Flag peaks above −3 dB #127`).

*Why:* the `/wayfinder` skill requires it ("a wall of `#42, #43, #44` is illegible"), and Waystation extends that skill.

*In practice:* a link's text is the name. Show the id only as the small `.id` span after it.

## 4. Use the skills' own words and pictures

Fog, frontier, destination, seam, tracer bullets, red and green all come from the skills, and the UI draws them literally:
- fog is a stippled texture
- the destination is a marked point
- the frontier is the edge of the known
- red and green test runs are hatched and solid marks

*Why:* someone who uses the skills already has this vocabulary. Renaming it would make them translate. Drawing it makes the skill easier to learn for someone new to it.

*In practice:* check [`../../CONTEXT.md`](../../CONTEXT.md) before naming anything. When the skills have no word, use the chart metaphor (course, thread, chronicle).

## 5. Steer in place, and show what will happen first

"Watch and steer" means every thing that waits on a person has its action right beside its context. Before a consequential action, the UI says what it will cause:
- the merge bar says what landing will unblock
- closing the last ticket lists the fog it clears
- the seam proposal explains the trade-off

Buttons say what happens ("Post resolution and close", "Approve and merge", "Send answer and resume").

*Why:* people trust an agent they can steer with confidence. Seeing consequences first keeps them from fighting the tool.

## 6. Most unblocking first

**Needs you** is ordered by how much each item unblocks, and each item says what it unblocks ("Unblocks 2 tickets and clears fog").

*Why:* when agents run in parallel, the person is the bottleneck. Their attention should go where it frees the most work.

## 7. Shape carries status; colour carries the course

Status is always a glyph shape paired with a word. There is no red, amber or green anywhere. The single accent colour, chart magenta, means only two things:
1. the **course** walked so far
2. the one primary action on a screen

*Why:*
- Colour-only status fails colour-blind users and WCAG 1.4.1.
- A traffic-light palette makes every screen look alarmed.
- Aviation GPS and nautical charts draw the planned course in magenta. Giving the accent that one meaning makes it read as a thread through the product rather than decoration.

*In practice:* see the glyph table in [`visual-language.md`](visual-language.md). Before adding colour anywhere, find the shape and word that say the same thing.

## 8. One primary action per screen

Each screen has one solid primary button for its most important action. Everything else is secondary, ghost or a text link. A long page may repeat its primary once, at the end.

*Why:* the accent budget in principle 7 depends on it, and one clear next step is what makes a screen feel calm.

## 9. Calm by default; motion that explains

Motion is only used to show change:
- the fog lifting
- the course drawing itself in
- a map replaying its history once per session
- the line drawing across home once per session

Nothing loops for decoration. The only continuous animation is the spinning "building" glyph, which means work is happening now. Every animation respects `prefers-reduced-motion`, and any intro can be skipped with a click or key press.

## 10. Provenance everywhere

Anything that was decided links back to where it was decided:
- a spec's implementation decisions point to the map tickets they came from
- stories point to the tickets that deliver them
- a PR's acceptance criteria point to the tests that prove them
- the **thread** traces any ticket from map to merge

*Why:* the skills keep each decision in exactly one place (the `/wayfinder` map is an index, not a store). Waystation makes those links easy to follow instead of copying the content around.

## 11. Stay faithful to the skills' process

Waystation never shortcuts what the skills require:
- A HITL ticket resolves only through a real exchange with the person. The agent never answers its own grilling.
- Charting resolves nothing.
- `/to-spec` writes without interviewing, but it does agree seams with the person.
- `/to-tickets` drafts go to the person to check before they publish.
- One ticket per session, except research.

When the UI makes something one click, the click starts the skill. It never replaces it.

## 12. Focus stays where you clicked

After a click on a selectable item (a map node, ticket card, session lane, desk item, or a sort or seam option), keyboard focus stays on that element. Handlers update the clicked element in place and never rebuild it with `innerHTML`. When an action replaces a whole panel, focus moves on purpose to the new panel's heading.

*Why:* this was checked on every turn of the prototype. Re-rendering the clicked control silently breaks keyboard navigation, and unit tests that call `focus()` directly never catch it. *Check:* dispatch a real click, assert `document.activeElement` is still the target, then send a key press.

---

## Design history: what was tried and why it changed

This history exists so the build doesn't repeat mistakes that were already found and fixed.

| Tried | What went wrong | What replaced it |
|---|---|---|
| A board with columns (the default in vibe-kanban and agent-orchestrator) | The user asked for the opposite of a board | The skill line and route band (principle 1) |
| A brick-red accent | A stock "editorial" colour with no meaning in this product; it wouldn't make anyone look twice | Chart magenta, meaning only the course and the primary action |
| An accent-coloured "Needs you" count and a primary "Open the desk" button on home, alongside the magenta tracks | Too many accent uses on one screen | The count is ink and the button is secondary |
| A dark theme at 15:1 body contrast on near-black | Halation: bright text glows and reads as blurry, especially with astigmatism | A charcoal ground with dimmed text at about 11:1. Quieter 1px rules on dark. The light theme also softened from 17:1 to about 14.5:1. |
| Oval clearings cut into the fog stipple behind fog notes | In dark mode each clearing showed a visible rim, or "ringing" | A tight letter halo in the background colour (cartographic label halo), with dimmer stipple in dark mode only |
| Map labels at the default canvas scale | About 11px on a 1440px laptop | Larger labels and a narrower side panel, landing around 13px |
| Ticket cards sized for short names | Long names clipped their third line | Taller cards with a three-line clamp |
| The handoff to `/to-spec` as a separate page, or only as a replay step | A separate page loses the map, and a replay can't be acted on | A live moment on the map itself: the last ticket closes, then the handoff happens in the side panel |
| A first-run setup checklist page | It reads like onboarding chores and repeats the navigation | The route band shows readiness per station, and the idea composer sits in the fog on a blank chart |
| A read-only list of the frontier after the breadth-first pass | It hides the most important judgement in charting | A Ticket-or-Fog sort that moves each question across the chart and teaches the skill's test: can it be stated precisely now? |
