---
type: reference
---
# Visual language

`assets/wayfarer.css` holds every value named here, so read the numbers there. This doc explains what each value is *for*, which isn't written in the CSS.

## Direction

The look is an editorial field journal: warm paper, ink, a serif for the names of things, and a single magenta for the course. The light theme is "the chart"; the dark theme is "the night chart", meaning the same chart read at night rather than an inverted palette.

It is deliberately light and quiet. Every comparable tool (vibe-kanban, agent-orchestrator) is dark and dense, so a calm paper surface is the first thing that sets Waystation apart.

## Tokens

There are six base tokens per theme, all in OKLCH. Every other tone is mixed from them with `color-mix()`, and the build keeps that model: no new base colours, no hex values.

| Token | Meaning |
|---|---|
| `--bg` | The page: paper, or charcoal at night |
| `--surface` | Raised panels, cards, inputs. Barely off the page. |
| `--fg` | Ink: body text, glyph fills, heavy marks |
| `--muted` | Secondary text and captions. Still AA or better on both grounds. |
| `--border` | Hairlines between regions |
| `--accent` | Chart magenta: the course, and the one primary action |

| Derived | Meaning |
|---|---|
| `--ink-2` | Softer ink for supporting prose and fog notes |
| `--wash` | The faintest tint: landed cards, linked rows, diff additions |
| `--hover` | Hover background. The step is larger on dark so it still reads. |
| `--line` | Pending tracks, dashed edges, underlines |
| `--rule` | Heavy rules and emphasis outlines. Ink in light mode, a quieter ink at night. |
| `--accent-hover` | Primary button hover |
| `--shadow` | The single soft shadow used on menus and the composer |

### Contrast targets

These were tuned on purpose, so don't push them higher:

| Text | Light | Dark |
|---|---|---|
| Body | about 14.5:1 | about 11:1 |
| Secondary | about 8.4:1 | about 6.1:1 |
| Smallest grey labels | 6.4:1 or better | 5.9:1 or better |
| Primary button label | about 6.0:1 | about 5.9:1 |

Body contrast is held *below* the maximum because very bright text on a dark ground halates: it glows and reads as blurry. The user saw this directly. Near-black ink on pure white glares the same way in reverse. The accessibility floor is still AA and above everywhere.

## Type

| Role | Stack | Used for |
|---|---|---|
| Display | Iowan Old Style, Charter, Georgia, serif. Weight 500. | The names of things (maps, tickets, specs, stations), headlines, fog notes (italic), resolutions |
| Body | System sans | Interface text, prose, controls |
| Mono | ui-monospace, JetBrains Mono, SF Mono, Cascadia Mono, Consolas | Skill names (`/tdd`), ids, worktrees, kickers, timestamps, numbers (`.num` uses tabular figures) |

Rules:
- A name is always serif. A skill is always mono. That pairing lets you tell *what* a thing is from *which skill* touched it at a glance.
- Kickers (small uppercase mono labels) introduce blocks: `.kicker` at 11.5px with 0.07em tracking.
- Nothing renders below 11px. Tiny grey mono text on Windows looked fuzzy, so every size of 10 to 10.5px was raised.
- On Windows the serif falls back to Georgia, whose thin strokes suffer most on dark grounds. Shipping a licensed serif webfont is an open question.

## Colour meaning

- **Accent:** only the course walked so far (tracks on the route band and home line, walked edges on a map, landed dependency wires on the ticket graph, the destination pulse) and the one primary button per screen. At most two uses per view.
- **Status:** always a glyph shape plus a word, never colour.
- **Hover:** moves the background lightness, or strengthens a border or underline. Text never gets lighter on hover.
- **Disabled:** controls use `aria-disabled="true"` and stay focusable. Disabled is the only state allowed to lower contrast.
- **Focus:** a 2px ink outline on every focusable element (`:focus-visible`).

## Status glyphs

This is one vocabulary on every screen. The classes live in `wayfarer.css` under "status glyphs". The same shape means the same kind of state, whatever the object.

| Glyph | Class | Ticket (build) | Map ticket | Elsewhere |
|---|---|---|---|---|
| Filled circle | `st-done` | Landed | Decided (closed) | A station that's done; a check that passed |
| Half-filled ring | `st-review` | Landing (in the merge queue) | — | A station with a PR waiting |
| Spinning ring | `st-building` | Building (session running) | Claimed | Agents working; a step in progress |
| Solid diamond | `st-ask` | Asked (a session ended to ask a question) | HITL ticket on the frontier, waiting on you | Anything in Needs you that needs an answer |
| Hollow diamond | `st-held` | Held (finished work waiting on your decision) | — | — |
| Bold ring | `st-take` | Takeable now (on the frontier, unclaimed) | AFK frontier ticket | "Ready to slice" and other next moves |
| Dashed ring | `st-blocked` | Blocked | Blocked | A skill that isn't installed (first run) |
| Thin ring | `st-pending` | — | Not yet on the map | A step not reached yet |
| Ring with a slash | `st-out` | — | Out of scope | — |

Every glyph sits next to a word. On a canvas, the glyph's `aria-label` or the element's label carries the word.

### Other marks

| Mark | Meaning |
|---|---|
| Hatched square `tr-red` / solid square `tr-green` | A failing or passing test run. The test rhythm strip shows a red before every green. |
| Stipple texture (`.fog`, `.fog-key`, the SVG `#stipple` pattern) | Fog: in scope, not yet specified |
| Ring with a centre dot (`.dest-mark`, `.mini-dest`) | The destination. Dashed and empty until it's named, filled once the way is clear. |
| Short vertical bar (`.s-flag`) | The Landed station, which is the end of the line |
| Checkbox `box` / `box.on` / `box.part` | An acceptance criterion that is not met, met, or met but weakly asserted |
| Beat marks: small ring, dash, outlined square, diamond | A session read something, noted something, refactored, or received a note from you |
| Diff sign cells: solid `+`, outlined `−`, struck-through text | Added or removed lines, shown by shape so the diff works without colour |

## Drawing charts

The map, the ticket graph and the first-run chart follow the same conventions:
- **Fixed canvas, scaled to fit.** Each chart is drawn at a fixed size (the map is 1180 × 700) and scaled down to its column by `WS.fitCanvas`, with a floor near 0.7. Below that floor, the viewport scrolls instead of shrinking the text.
- **Edges:**
  - A walked edge (course or met dependency) is a solid magenta line, about 2.25px.
  - An open dependency is a dashed muted line.
  - A start-line edge is a thin `--line` stroke.
  - An edge toward the destination is dotted until the way is clear, then it turns magenta.
  - Selecting a node makes its edges "hot": thicker, and drawn on top.
- **Labels** sit on a small plate in the page colour so edges pass behind them cleanly.
- **Fog** is a band of stipple under a translucent page-colour wash, faded at both edges with a mask. Text in fog gets a letter halo (a stack of `text-shadow` in `--bg`), never a cut-out shape. The stipple is dimmer in dark mode.
- **Layout direction** is always left to right: the start line (where the effort began) on the left, the destination on the right, and out-of-scope work in a tray *past* the destination.

## Motion

| Motion | Where | Rule |
|---|---|---|
| Spinning ring | `st-building` | The only continuous animation. It means work is happening now. |
| Line draws in | Home, the line | Once per browser session (`wayfarer.intro.line`) |
| Map replays its story | Wayfinder map | Once per session per map (`wayfarer.intro.<effort>`). About 1.1s per step. Any click or key outside the replay bar skips to now. |
| Fog lifts, course draws, destination pulses | The way is clear | Plays once, on the close that clears the way. Takes about 2.5s. |
| Fog recedes to a band | First run, after mapping the frontier | About 1.5s |
| Nodes move between ticket and fog | First run, Ticket or Fog sort | About 0.7s, following the click |
| Route track draws to the next station | Handoff; spec published | About 0.9s |
| Panel blocks rise in | Handoff panel, sort list | Staggered 0.45 to 0.55s |
| Theme fade | Theme toggle | 0.3s |

Everything above collapses to an instant state change under `prefers-reduced-motion`.

## Themes

- **Toggle:** the sun/moon button in the top bar. It follows the system setting until the user picks a theme, then remembers the choice (`localStorage` key `wayfarer.theme`).
- **No flash on load:** each page's `<head>` applies the saved theme before first paint.
- **What changes at night:** the six tokens, plus larger hover steps, quieter heavy rules, and dimmer fog stipple. Nothing else, and no screen needs theme-specific markup.

## Responsive

- **Target:** laptop and desktop, 1280 to 1920px wide. Check every screen at 1440 × 900 first.
- **Below 920px:**
  - side panels stack under their canvas
  - the route band wraps to three columns
  - charts scroll sideways inside their viewport
  - touch targets grow to 44px
- **Mobile layouts:** not designed yet. This is an open question per screen.
