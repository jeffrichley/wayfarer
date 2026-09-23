import { type ReactNode, useState } from "react";

import type { ChronicleLine, Mention } from "../api";
import { Button, type ButtonProps } from "../Button";
import { Chronicle, Line } from "../Chronicle";
import { Criteria } from "../Criteria";
import { Frame, Pane, Split } from "../Frame";
import { type Glyph, State, TestRun, TestRuns } from "../State";
import { type Step, Thread } from "../Thread";
import { Chip, Kicker, Meta, Named, Rule } from "../Type";
import styles from "./Gallery.module.css";

// Every primitive in every state, on one page. A ticket that lands a widget adds
// a section here, and the same specimens, drawn from the prototype's markup, to
// tests/prototype_gallery.html; the snapshot check compares the two by name.

// The glyph vocabulary, each with the word it carries on the ticket graph.
const GLYPHS: [Glyph, string][] = [
  ["done", "Landed"],
  ["review", "Landing"],
  ["building", "Building"],
  ["ask", "Asked"],
  ["held", "Held"],
  ["take", "Takeable"],
  ["blocked", "Blocked"],
  ["pending", "Not reached yet"],
  ["out", "Out of scope"],
];

// Each button variant with the words it carries in the prototype.
const VARIANTS: [ButtonProps["variant"], string][] = [
  ["primary", "Arm the cascade"],
  ["secondary", "Review PR #141"],
  ["ghost", "Queue an agent"],
];
const SIZES = [
  ["", {}],
  ["-small", { small: true }],
  ["-arrow", { arrow: true }],
] as const;

// #128's thread as the ticket graph's panel draws it, mid-build.
const THREAD: Step[] = [
  {
    skill: "/wayfinder",
    name: <a className="nm" href="#112">ACX compliance before delivery</a>,
    meta: "What does ACX reject? · How should a failing chapter explain itself?",
    glyph: "done",
    word: "Landed",
  },
  {
    skill: "/to-spec",
    name: <a className="nm" href="#124">Pre-delivery compliance checks</a>,
    meta: "Story 5",
    glyph: "done",
    word: "Landed",
  },
  {
    skill: "/to-tickets",
    name: <Named name="Flag a noise floor above −60 dB" id={128} href="#128" />,
    meta: "After Flag loudness",
    glyph: "done",
    word: "Landed",
  },
  {
    skill: "/tdd",
    name: <a className="nm" href="#wt">wt/noise-floor</a>,
    meta: "Claude Code · running now",
    glyph: "building",
    word: "Building",
  },
  { skill: "/code-review", name: "No PR yet", glyph: "pending", word: "Not reached yet" },
  { skill: "merge", name: "Not landed", glyph: "pending", word: "Not reached yet" },
];

const CRITERIA = [
  "Measure the noise floor of every chapter",
  "Chapters above −60 dB fail the check",
  "Failures explain the value, the limit, and the timestamp",
  "The clean fixture passes",
];

// The chronicle's sample effort and tickets, from the prototype's ACX effort.
const EFFORT: Mention = { number: 124, title: "Pre-delivery compliance checks" };
const ANALYSIS: Mention = { number: 125, title: "Extract the audio analysis pass from the render worker" };
const LOUDNESS: Mention = { number: 126, title: "Flag loudness outside −23 to −18 dB RMS" };
const PEAKS: Mention = { number: 127, title: "Flag peaks above −3 dB" };
const NOISE_FLOOR: Mention = { number: 128, title: "Flag a noise floor above −60 dB" };
const LONG_CHAPTERS: Mention = { number: 129, title: "Flag chapters longer than 120 minutes" };
const CREDITS: Mention = { number: 130, title: "Require opening and closing credits" };
const ROOM_TONE: Mention = { number: 131, title: "Check room tone at the head and tail of each chapter" };
const MY_BOOKS: Mention = { number: 132, title: "Show compliance status on My Books" };

const MIRA = { login: "mira" };

// A line at a local time, in September 2026 unless it says otherwise, so it reads
// the same in any timezone.
function line(
  id: string,
  day: number,
  time: string,
  moved: ChronicleLine["moved"],
  [year, month] = [2026, 8],
): ChronicleLine {
  const [hours, minutes] = time.split(":").map(Number);
  const at = new Date(year, month, day, hours, minutes).toISOString();
  return { kind: "chronicle_line", id, at, effort: EFFORT, moved };
}

// Every kind of line, in every voice and every shape of what it caused.
const LINES: ChronicleLine[] = [
  line("line-taken", 15, "09:41", { kind: "taken", ticket: NOISE_FLOOR, by: "wayfarer" }),
  line("line-taken-you", 15, "09:41", { kind: "taken", ticket: CREDITS, by: "you" }),
  line("line-taken-someone", 15, "09:41", { kind: "taken", ticket: CREDITS, by: MIRA }),
  line("line-asked", 15, "09:18", {
    kind: "asked",
    ticket: CREDITS,
    gist: "Should DOCX books without credits fail or warn?",
  }),
  line("line-answered", 15, "09:30", { kind: "answered", ticket: CREDITS, by: "you" }),
  line("line-answered-someone", 15, "09:30", {
    kind: "answered",
    ticket: CREDITS,
    by: MIRA,
  }),
  line("line-held", 15, "08:12", {
    kind: "held",
    ticket: LONG_CHAPTERS,
    reason: "Its tests were still red when the session ended.",
  }),
  line("line-retried", 15, "08:20", { kind: "retried", ticket: LONG_CHAPTERS, over: false }),
  line("line-retried-over", 15, "08:20", { kind: "retried", ticket: LONG_CHAPTERS, over: true }),
  line("line-landed", 15, "07:48", {
    kind: "landed",
    ticket: PEAKS,
    by: "wayfarer",
    freed: [],
    started: [],
  }),
  line("line-landed-freed", 14, "16:40", {
    kind: "landed",
    ticket: ANALYSIS,
    by: "wayfarer",
    freed: [LOUDNESS, PEAKS],
    started: [],
  }),
  line("line-landed-folded", 14, "22:14", {
    kind: "landed",
    ticket: LOUDNESS,
    by: "wayfarer",
    freed: [NOISE_FLOOR, LONG_CHAPTERS, CREDITS],
    started: [NOISE_FLOOR, LONG_CHAPTERS],
  }),
  line("line-landed-all", 15, "07:48", {
    kind: "landed",
    ticket: PEAKS,
    by: "wayfarer",
    freed: [MY_BOOKS],
    started: [MY_BOOKS],
  }),
  line("line-landed-by-hand", 15, "07:48", {
    kind: "landed",
    ticket: PEAKS,
    by: "you",
    freed: [],
    started: [],
  }),
  line("line-landed-by-someone", 15, "07:48", {
    kind: "landed",
    ticket: PEAKS,
    by: MIRA,
    freed: [],
    started: [],
  }),
  line("line-closed", 15, "11:02", { kind: "closed", ticket: ROOM_TONE, by: "you" }),
  line("line-closed-someone", 15, "11:02", { kind: "closed", ticket: ROOM_TONE, by: MIRA }),
  line("line-armed", 13, "15:30", { kind: "armed", started: [NOISE_FLOOR, LONG_CHAPTERS] }),
  line("line-armed-idle", 13, "15:30", { kind: "armed", started: [] }),
  line("line-published", 14, "10:20", { kind: "published", tickets: 9, freed: [ANALYSIS], started: [ANALYSIS] }),
  line("line-ready", 15, "12:00", { kind: "ready_to_ship" }),
  line("line-shipped", 15, "12:30", { kind: "shipped" }),
];

function sample(id: string): ChronicleLine {
  const found = LINES.find((l) => l.id === id);
  if (found === undefined) {
    throw new Error(`no sample line ${id}`);
  }
  return found;
}

// Home's chronicle on Tuesday 15 September: today and yesterday, with three
// earlier days, gaps between them and the last in the year before, to load one
// at a time.
const NOW = new Date(2026, 8, 15, 10, 0);
const RECENT = ["line-taken", "line-asked", "line-landed", "line-landed-folded", "line-landed-freed", "line-published"];
const EARLIER = [
  [sample("line-armed")],
  [line("friday", 11, "11:05", { kind: "taken", ticket: ANALYSIS, by: "you" })],
  [line("last-year", 31, "16:00", { kind: "published", tickets: 9, freed: [], started: [] }, [2025, 11])],
];

function ChronicleSpecimen() {
  const [loaded, setLoaded] = useState(0);
  const lines = [...RECENT.map(sample), ...EARLIER.slice(0, loaded).flat()];
  return (
    <Chronicle
      lines={lines}
      now={NOW}
      earlier={loaded < EARLIER.length ? () => setLoaded(loaded + 1) : undefined}
    />
  );
}

const TOKENS = [
  "--bg",
  "--surface",
  "--fg",
  "--muted",
  "--border",
  "--accent",
  "--ink-2",
  "--wash",
  "--hover",
  "--line",
  "--rule",
  "--accent-hover",
  "--shadow",
];

function Specimen({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className={styles.specimen} data-specimen={name}>
      {children}
    </div>
  );
}

// Enough lines that a region overflows, so it can be seen to scroll on its own.
function Filler({ what }: { what: string }) {
  return Array.from({ length: 15 }, (_, i) => (
    <p key={i} style={{ padding: "4px 20px" }}>
      {`Line ${i + 1} of ${what}.`}
    </p>
  ));
}

// Stand-ins for the top bar and the route band, which are their own widgets.
function StandIn({ children }: { children: string }) {
  return (
    <p className="meta" style={{ padding: "12px 24px", borderBottom: "1px solid var(--border)" }}>
      {children}
    </p>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

// The theme is set on the root, as the page's head script sets it on load; the
// shell's toggle, which remembers the choice, is its own widget.
function setTheme(theme: "light" | "dark") {
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
}

export function Gallery() {
  return (
    <main className={styles.page} data-piece="gallery">
      <header className={styles.head}>
        <h1>Gallery</h1>
        <div className={styles.themes}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setTheme("light")}>
            The chart
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setTheme("dark")}>
            The night chart
          </button>
        </div>
      </header>

      <Section title="Tokens">
        <div className={styles.swatches}>
          {TOKENS.map((token) => (
            <div key={token} className={styles.swatch}>
              <div className={styles.chip} style={{ background: `var(${token})` }} />
              <code className="meta">{token}</code>
            </div>
          ))}
        </div>
      </Section>

      <Section title="State">
        <div className={styles.legend}>
          {GLYPHS.map(([glyph, word]) => (
            <Specimen key={glyph} name={`glyph-${glyph}`}>
              <State glyph={glyph}>{word}</State>
            </Specimen>
          ))}
        </div>
        <div className={styles.legend}>
          {GLYPHS.map(([glyph, word]) => (
            <Specimen key={glyph} name={`glyph-${glyph}-lg`}>
              <State glyph={glyph} large>
                {word}
              </State>
            </Specimen>
          ))}
        </div>
        <div className={styles.legend}>
          <Specimen name="run-red">
            <TestRun result="red">Failing</TestRun>
          </Specimen>
          <Specimen name="run-green">
            <TestRun result="green">Passing</TestRun>
          </Specimen>
        </div>
      </Section>

      <Section title="Type">
        <div className={styles.row}>
          <Specimen name="type-kicker">
            <Kicker>/to-tickets · 9 tracer bullets</Kicker>
          </Specimen>
          <Specimen name="type-display">
            <h2>Pre-delivery compliance checks</h2>
          </Specimen>
          <Specimen name="type-body">
            <p>A ticket reaches the frontier when every ticket feeding into it has landed.</p>
          </Specimen>
          <Specimen name="type-meta">
            <Meta>Holds up 4 tickets · 1 starts the moment it lands</Meta>
          </Specimen>
          <Specimen name="type-name">
            <Named name="Warn when no retail sample is chosen" id={127} href="#127" />
          </Specimen>
          <Specimen name="type-skill">
            <span className="skill">/code-review</span>
          </Specimen>
          <Specimen name="type-chip">
            <Chip>AFK</Chip>
          </Specimen>
          <Specimen name="type-num">
            <span className="num">10:20</span>
          </Specimen>
          <Specimen name="type-rule">
            <div style={{ width: 200 }}>
              <Rule />
            </div>
          </Specimen>
        </div>
      </Section>

      <Section title="Names">
        <div className={styles.row}>
          <Specimen name="name-plain">
            <Named name="Warn when no retail sample is chosen" id={127} />
          </Specimen>
          <Specimen name="name-row">
            <span style={{ fontSize: "13.5px" }}>
              <Named name="Flag peaks above −3 dB" id={127} href="#127" />
            </span>
          </Specimen>
          <Specimen name="name-line">
            <p>
              <Named name="Flag peaks above −3 dB" id={127} href="#127" /> finished its session and
              opened PR #141.
            </p>
          </Specimen>
          <Specimen name="name-head">
            <h2>
              <Named name="Flag peaks above −3 dB" id={127} href="#127" />
            </h2>
          </Specimen>
        </div>
      </Section>

      <Section title="Buttons">
        {VARIANTS.map(([variant, label]) => (
          <div key={variant} className={styles.row}>
            {SIZES.flatMap(([size, props]) =>
              [false, true].map((disabled) => (
                <Specimen
                  key={`${size}${disabled}`}
                  name={`button-${variant}${size}${disabled ? "-disabled" : ""}`}
                >
                  <Button variant={variant} {...props} disabled={disabled}>
                    {label}
                  </Button>
                </Specimen>
              )),
            )}
          </div>
        ))}
        <div className={styles.row}>
          <Specimen name="button-link">
            <Button variant="secondary" arrow href="#desk">
              Open the desk
            </Button>
          </Specimen>
          <Specimen name="button-link-disabled">
            <Button variant="secondary" arrow href="#desk" disabled>
              Open the desk
            </Button>
          </Specimen>
        </div>
      </Section>

      <Section title="Frames">
        <div className={styles.row}>
          <Specimen name="frame">
            <div className={styles.frame}>
              <Frame bar={<StandIn>The top bar</StandIn>} route={<StandIn>The route band</StandIn>}>
                <Pane>
                  <Filler what="the page" />
                </Pane>
              </Frame>
            </div>
          </Specimen>
          <Specimen name="frame-no-route">
            <div className={styles.frame}>
              <Frame bar={<StandIn>The top bar</StandIn>}>
                <Pane>
                  <Filler what="the page" />
                </Pane>
              </Frame>
            </div>
          </Specimen>
          <Specimen name="split-left">
            <div className={styles.frame}>
              <Frame bar={<StandIn>The top bar</StandIn>} route={<StandIn>The route band</StandIn>}>
                <Split left={{ label: "The queue", width: 240, children: <Filler what="the side" /> }}>
                  <Filler what="the page" />
                </Split>
              </Frame>
            </div>
          </Specimen>
          <Specimen name="split-right">
            <div className={styles.frame}>
              <Frame bar={<StandIn>The top bar</StandIn>} route={<StandIn>The route band</StandIn>}>
                <Split right={{ label: "The detail", width: 260, children: <Filler what="the side" /> }}>
                  <Filler what="the page" />
                </Split>
              </Frame>
            </div>
          </Specimen>
        </div>
      </Section>

      <Section title="Test runs">
        <Specimen name="runs">
          <TestRuns runs={["red", "green", "red", "red", "green"]} />
        </Specimen>
      </Section>

      <Section title="Thread">
        <Specimen name="thread">
          <div style={{ width: 340 }}>
            <Thread steps={THREAD} />
          </div>
        </Specimen>
      </Section>

      <Section title="Chronicle lines">
        <div className={styles.lines}>
          {LINES.map((l) => (
            <Specimen key={l.id} name={l.id}>
              <ol className={styles.chronicle}>
                <Line line={l} />
              </ol>
            </Specimen>
          ))}
        </div>
      </Section>

      <Section title="Chronicle">
        <Specimen name="chronicle">
          <div className={styles.chronicle}>
            <ChronicleSpecimen />
          </div>
        </Specimen>
      </Section>

      <Section title="Acceptance criteria">
        <Specimen name="criteria">
          <div style={{ width: 340 }}>
            <Criteria criteria={CRITERIA} />
          </div>
        </Specimen>
      </Section>
    </main>
  );
}
