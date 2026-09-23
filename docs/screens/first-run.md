---
type: reference
status: draft
---
# First run

**Prototype:** `first-run.html` · **Station:** `/wayfinder` · **Arrive from:** the repo switcher, choosing a repo with no maps (the sample is *madrigal*) · **Leave to:** the new map, once charted

## Intent

A repo just connected, with nothing charted. This screen does two jobs without feeling like onboarding:
1. It shows whether the repo is **ready** for the skill line: what's installed, what's configured, and what's missing.
2. It gets the person from a **loose idea** to a **charted map** by walking the real `/wayfinder` charting steps with them: name the destination, map the frontier, create the map.

The emotional target is a blank nautical chart. Everything is fog, the destination isn't named yet, and there's one invitation: *what's too big for one agent session?*

## Layout

The layout matches the map screen, so the first map is born in the place it will live:
- **Top bar** with the repo switcher showing `madrigal`, and **route band** in readiness mode.
- **Chart column** (`blank-chart`):
  - a head (kicker, title, lead)
  - the chart canvas
  - the **charting steps** bar (`charting-steps`) where the map's replay bar normally sits
- **Side panel** (`first-run-panel`): readiness at first, then the charting session.

## Pieces

### Route band in readiness mode
- **What each station shows:** whether its skill is installed ("Installed", "Not installed", "GitHub · main" for Landed) instead of work.
- **Glyphs:** an installed skill gets a thin ring (nothing walked yet); a missing one gets a dashed ring, with its output line in ink so it stands out.
- **Sample gap:** `/code-review` is missing. The station's title says what that means: add it from mattpocock/skills and agents review PRs before you do.
- **After charting:** the `/wayfinder` station turns active ("Map #38 · 2 researching").

*Why readiness lives in the route band:* the band is already the product's spine. Showing readiness per station answers "can this repo run the skill line?" in the same place that will later show the work, with no separate setup checklist.

### The blank chart (canvas)
- **Start line:** on the left, labelled "Here · madrigal today".
- **Fog:** covers the whole sheet, labelled "Not yet charted".
- **Destination:** on the right, a **dashed, empty ring** reading "Not named yet".
- **Course hint:** a faint dotted line from start to destination. It says *there is a way; it isn't visible yet*.

### Loose-idea composer (`loose-idea`)
A card sitting *in the fog*, in the middle of the chart. It contains:
- kicker "Start from a loose idea"
- serif prompt "What's too big for one agent session?"
- a textarea
- a text link, **Use an example idea** (`use-example-idea`)
- the primary **Start charting** (`start-charting`), with "Runs /wayfinder in Claude Code. You name the destination together first."

Submitting an empty idea shows "Write the idea first. A rough sentence is enough." and focuses the field. On mobile the composer sits above the chart instead of on it.

*Why the composer is in the fog:* the idea literally starts in the unknown. The page's one primary action is the invitation.

### Readiness panel (before charting)
- **Heading:** "Ready for the skill line", explaining that Waystation read what `/setup-matt-pocock-skills` wrote.
- **Setup it found** (`setup-found`): issue tracker, triage labels, domain docs, Wayfinder labels ("Created with your first map", shown as pending rather than missing), and the missing `/code-review` with its consequence.
- **Not every idea needs a map** (`skip-the-map`): if the work is already clear and fits one session, skip charting and run `/to-spec` where you talked it through. Specs labelled `ready-for-agent` join the line at `/to-tickets` on their own.
- **How a map fills in** (`map-key`): the destination, frontier, blocked, fog and decided glyphs, each with a one-line meaning. A first-time user learns the vocabulary here.

*Why include "Not every idea needs a map":* `/wayfinder` itself says that if charting surfaces no fog, you don't need a map. The first screen shouldn't push people into ceremony the skill says to skip.

### Charting steps bar (`charting-steps`)
- **The five steps** of the skill's "Chart the map" mode: 1 Name the destination · 2 Map the frontier · 3 Create the map · 4 Wire the tickets · 5 Fire research.
- **Step glyphs:** pending ring, diamond while it's your turn, spinning ring while the agent works, filled when done.
- **Caption:** a sentence under the steps that says what's happening and whose turn it is.
- **Closing line:** "Charting resolves nothing, so it ends here."

### Destination session (`destination-session`)
Appears after Start charting. The composer fades out, the chart head shows the idea in italic, and the destination reads "Naming it with you". The panel shows:
- **The conversation:** your idea, then `/grilling` asking what reaching the end looks like, with its recommendation.
- **Three destination options** as radio cards, one per kind the skill allows. Each card holds a drafted destination sentence specific to the idea:
  - **A spec** ("…ready for /to-spec"), recommended and preselected
  - **A decision** ("…locked before any build is planned")
  - **A change made in place** ("…migrated in place")
- **"Or say it in your own words":** a textarea that, if filled, is used instead of the options.
- **Set the destination** (`set-destination`):
  - locks the choices and turns the button into a disabled "Destination set"
  - fills the destination ring on the chart and writes its sentence
  - adds a `/domain-modeling` message about the terms written to the map's Notes
  - reveals **Map the frontier** (`map-the-frontier`)

### Ticket or fog (`ticket-or-fog`)
Appears after Map the frontier.
- **On the chart:** the fog **recedes** from the whole sheet to a band before the destination, and the questions the breadth-first pass found appear:
  - **tickets** as nodes near the start line
  - **fog** as italic notes in the band
  - start, dependency and to-destination edges drawn between them
- **In the panel:**
  - heading "Ticket or fog?", with the skill's test in plain words: *a question becomes a ticket if it can be stated precisely now, even if it can't be answered yet*
  - a count ("4 tickets · 3 patches of fog")
  - a list of candidates (`candidate-<i>`). Each shows its text, its type and mode (or "Fog · coarser than a ticket"), and a **Ticket | Fog** segmented control.
- **Flipping a candidate:**
  - moves it across the chart: a node glides into the fog band as a note, or out of the fog as a node
  - re-lays out the columns: blocked tickets sit beside their blocker, and a crowded column splits in two
  - redraws the edges
  - keeps focus on the clicked segment
- **Primary:** **Create the map** (`create-map-button`), with a note that tickets are created as child issues, blocking is wired in a second pass, and research starts straight away. With nothing sorted as a ticket, it explains that the way is already clear and a spec is the better route.

*Why a sort instead of a list:* deciding what is sharp enough to ticket is the most important judgement in charting, and it's the person's to make. Moving each question across the chart makes the frontier and the fog something you can see and change.

### Creating the map
- **Button:** becomes "Creating the map" and the sort locks.
- **Steps animate in order:**
  - **Create the map:** the chart head becomes "/wayfinder · map #38 · charted today" and the map's title
  - **Wire the tickets:** nodes get issue numbers
  - **Fire research:** research nodes start spinning
- **Glyphs settle into real states:** research → claimed by a research subagent, HITL on the frontier → waiting on you, anything with a ticketed blocker → blocked.
- **The panel becomes the new map's body** (`new-frontier`): the title, "Charted today. Charting resolves nothing…", Destination, Notes, the tickets on the map with their states, Not yet specified, and "Decisions so far · 0", which names the first frontier ticket to work next.
- **Top bar and route band** update: the repo reads "1 map charted" and `/wayfinder` is active.

## Flows

1. **Readiness check:** read the route band and the setup panel, and fix any gaps, or skip the map entirely.
2. **Chart a map:** write the idea → Start charting → pick or write the destination → Map the frontier → sort Ticket or Fog → Create the map → the chart becomes the map.
3. **Revisiting:** once charted, the page opens straight on the charted map.

## Why it looks this way

- **The same frame as the map screen:** the chart, the steps bar where the replay will be, and the side panel. The first map's birth happens where it will live, and nothing moves when the map exists.
- **One primary action at each stage:** Start charting, then Set the destination, then Map the frontier, then Create the map. Earlier buttons become disabled and secondary, and stay where they were so focus isn't lost.
- **Focus handling:** moving to a new stage replaces the panel and moves focus to its heading on purpose.
- **The fog receding** is this screen's one flourish. It marks the moment the unknown gets a shape.

## Prototype shortcuts

- **Scripted session:** the charting session always follows the sample idea (Madrigal voices beyond English), even if the person types something else. Candidate questions, destination sentences, the map number (#38) and issue numbers are all fixed.
- **Storage:** nothing is saved. The whole flow plays through on this page, and a reload starts over from the blank chart.
- **No link out:** the charted map isn't linked to `wayfinder-map.html`, which only knows the Galley maps. In the real build, this page *becomes* that map.

## Open questions

- Whether destination-naming and the breadth-first pass are real multi-turn conversations in the panel, or structured choices as prototyped. How does free text flow into the running `/wayfinder` session?
- What if the person disagrees with a candidate's type or blocker? The sort only moves things between ticket and fog.
- Readiness detection: where installed skills are found, and whether Waystation offers to run `/setup-matt-pocock-skills` when setup is missing.
- Connecting a repo in the first place (OAuth, local path), which comes before this screen and isn't designed.
- A repo that has specs but no maps: does first run show them, or go straight to the line?
