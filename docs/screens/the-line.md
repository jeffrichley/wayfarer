---
type: reference
---
# The line (home)

**Prototype:** `index.html` · **Station:** all of them · **Arrive from:** the wordmark, or opening the app · **Leave to:** any effort's current station, the desk, a running session

## Intent

Home answers three questions in the order a person asks them when they come back to the repo:
1. **What changed while I was away?** (the masthead)
2. **Where is everything on the line?** (the line)
3. **What needs me, and what is running?** (Needs you, and At work)

It's the only screen with no route band, because it shows *every* effort's route at once. The line itself is a route band for each effort, stacked.

## Layout

The page is a single column that scrolls, capped at about 1240px:
1. **Masthead** (`masthead`): the headline and standfirst on the left, the dateline on the right, and a heavy rule under them.
2. **The line** (`the-line`): a section head with a glyph legend, then one row per effort across six station columns.
3. **Lower area**, in two columns:
   - left, wider: **the chronicle** (`chronicle`)
   - right: **Needs you** (`needs-you-panel`), then **At work** (`agents-at-work`)

## Pieces

### Masthead (`masthead`)
- **Kicker:** "galley · the story so far".
- **Headline:** one serif sentence, under 14 words, about the most important change since the last visit ("One ticket landed overnight, and an agent has stopped to ask you something."). It leads with the thing that needs the person.
- **Standfirst:** one or two sentences placing each active effort ("Two agents are still building ACX compliance before delivery. Choosing the retail sample is one decision from a clear way…"). In the prototype it changes with demo progress.
- **Dateline:** the day in serif, then the time and "N efforts moving" in mono.

*Why a newspaper masthead:* it's principle 2, tell the story. Coming back to a repo where agents worked overnight is like picking up the morning paper: you want the lead story first, not a grid of numbers.

### The line (`the-line`)
- **Legend:** decided or landed, agent working, waiting on you, takeable, blocked, fog.
- **Header row:** the six stations, each with its skill in mono above its name in serif.
- **One row per effort** (`line-acx`, `line-casting`, `line-retail-sample`, `line-upload-states`):
  - **Effort cell:**
    - The name in serif links to the station where the effort's frontier is: ACX goes to live build, and a charting effort goes to its map.
    - Below it, a meta line: "Map #112 · charted 3 Sep".
  - **Station cells:** each shows a **cluster** of small glyphs, one per ticket at that station, and a **caption** in words ("2 building · **1 asking you**"). Anything that needs the person is bold in the caption. The cluster links to that station's screen.
    - The map station's cluster shows decisions, frontier tickets and fog marks.
    - The Landed cluster shows landed tickets.
  - **Track:** a line through the row behind the clusters:
    - **magenta and solid** up to the furthest station the effort has reached
    - **dashed** beyond it
    - **ink** (not magenta) for an effort that has fully landed, so finished work rests and active courses stand out
  - **Stations the effort hasn't reached** show a small hollow marker on the dashed track.
- **Draw-in:** the tracks draw in left to right and the clusters arrive after them, staggered by row and column. This plays once per browser session and never under reduced motion.

*Why clusters of glyphs instead of counts:* the shape of a cluster shows its make-up at a glance. Three spinning rings and a diamond read as "busy, and one needs me" before you read a word. The caption carries the exact words for anyone who needs them.

### The chronicle (`chronicle`)
- **Grouping:** entries grouped by day ("Today", "Yesterday · Monday 14 September"), newest first.
- **Each entry:** the time in mono, a status glyph, one sentence that names things by name (ticket and map names are links), and the effort's name on the right. Not the skill that acted: tickets moving, not stages ([The chronicle](https://github.com/jeffrichley/wayfarer/issues/22)).
- **Summaries:** entries summarise rather than log ("*Flag loudness* landed. Three tickets reached the frontier, and two agents picked them up.").
- **Demo actions:** merges, answers, closes and similar actions add "now" entries at the top.

### Needs you (`needs-you-panel`)
- **Order:** most unblocking first.
- **Each item** (`need-<key>`):
  - a glyph (half ring for a review, diamond for anything waiting on an answer)
  - kind · effort in mono uppercase
  - the item's name in serif
  - what's being asked
  - what it unblocks, on the right ("Unblocks 2 tickets + fog", "Clears the way")
- **Where items go:** each item links to its desk item, or to the map for map work.
- **Foot:** "Answers post back to the tracker as comments." with a secondary **Open the desk** (`open-desk`).
- **Empty state:** "Nothing is waiting on you. Agents will stop here when they need a decision." The foot hides.

### At work (`agents-at-work`)
- **Contents:** every running session and research subagent.
- **Each entry:** a spinning glyph, the ticket name linking to its session in live build, and "wt/noise-floor · 3 of 4 criteria" or "Research subagent · research/voice-consistency".

## Flows

- **Coming back after time away:** read the headline, check the line for anything bold, and open the top Needs-you item.
- **Checking on one effort:** click its name, which goes where its frontier is, or click the cluster at a particular station.

## Why it looks this way

- **Paper and editorial type:** home should feel like reading, not monitoring.
- **One primary action at most, and in the prototype none:** "Open the desk" is secondary. The magenta tracks already use the accent, so a primary button would push the screen past the accent budget (principles 7 and 8).
- **Needs you beside the chronicle rather than above the line:** the headline already names the most urgent thing. Putting Needs you first would turn home into an inbox.

## Prototype shortcuts

- The headline is fixed text. The standfirst is assembled from a few fixed phrasings.
- Station clusters come from the sample tickets. The casting and upload-states rows are hand-authored.
- The chronicle entries are hand-written sample sentences.
- Below 920px the line scrolls sideways (minimum width 860px) and the lower area stacks.

## Open questions

- How the line scales past about 6 efforts: grouping, collapsing landed efforts, or ageing them off after some days.
- How a cluster reads when a station holds 30 tickets: aggregate glyphs, or show counts past a threshold?
- A real mobile layout. Today it's a sideways-scrolling table.
