import type { ReactNode } from "react";

import { Button, type ButtonProps } from "../Button";
import { Criteria } from "../Criteria";
import { Diff, type FileDiff, type Line } from "../Diff";
import { Frame, Pane, Split } from "../Frame";
import { type Need, NeedRow, NeedsList, QueueItem } from "../NeedsYou";
import { type Question, QuestionCard } from "../Question";
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

// One item of each kind Needs you has in this slice, across three efforts. The
// question is also shown resolved, and the review open on the desk.
const QUESTION: Need = {
  kind: "question",
  effort: "ACX compliance",
  ticket: { name: "Require opening and closing credits", id: 130 },
  question: "Should DOCX books without credits fail or warn?",
  holdsUp: 4,
  starts: 2,
};
const REVIEW: Need = {
  kind: "review",
  effort: "ACX compliance",
  ticket: { name: "Flag peaks above −3 dB", id: 127 },
  holdsUp: 1,
  starts: 0,
};
const NEEDS: Need[] = [
  { kind: "environment", reason: "Docker stopped answering; two tickets went back on the frontier" },
  QUESTION,
  {
    kind: "held",
    effort: "ACX compliance",
    ticket: { name: "Check room tone at the head and tail of each chapter", id: 131 },
    reason: "/code-review found a gap against the spec that blocks landing",
    holdsUp: 3,
    starts: 1,
  },
  REVIEW,
  { kind: "drafts", effort: "Retail sample", spec: "Retail sample suggestions", drafted: 6 },
  { kind: "ship", effort: "Voice casting", name: "Per-chapter voice casting" },
  { kind: "orphan", effort: "ACX compliance", ticket: { name: "Flag a noise floor above −60 dB", id: 128 } },
  {
    kind: "closed",
    effort: "ACX compliance",
    ticket: { name: "Flag chapters longer than 120 minutes", id: 129 },
  },
];

// #130's question, as the prototype asks it (WS.TICKETS in assets/wayfarer.js).
const ASKED: Question[] = [
  {
    text: "DOCX manuscripts don't mark front and back matter, so for those books I can only guess where credits would be. Should a DOCX book with no credits I can find fail like EPUB, or warn so the author can confirm?",
    options: [
      {
        label: "Fail, same as EPUB",
        consequence: "Stricter. Some DOCX books with real credits may fail until the author marks them.",
      },
      {
        label: "Warn, and ask the author to confirm",
        consequence: "Export stays unlocked for this check once they confirm credits are there.",
      },
    ],
  },
];

// As many questions as one ask carries, each with as many options as it can.
const ASKED_FOUR: Question[] = [
  {
    text: "Room tone at the head of a chapter can run long. Should more than one second fail the check, or only less than half a second?",
    options: [
      { label: "Both fail", consequence: "Matches ACX's wording. Some narrators' long heads will need trimming." },
      { label: "Only too little fails", consequence: "Long heads pass. A later check can warn about them." },
    ],
  },
  {
    text: "Where should a failing chapter say how much tone it found?",
    options: [
      { label: "In the check's line", consequence: "One place to read it, beside the pass or fail." },
      { label: "In the chapter's detail", consequence: "The check's line stays short; the number is a click away." },
      { label: "Both", consequence: "Repeats the number, so the two must stay in step." },
    ],
  },
  {
    text: "A chapter with no audio at all: does it fail room tone, or is that another check's job?",
    options: [
      { label: "Fail room tone", consequence: "The author sees one more failure for the same chapter." },
      { label: "Leave it to another check", consequence: "Room tone skips empty chapters and says so." },
    ],
  },
  {
    text: "Which chapters does the check read?",
    options: [
      { label: "Every chapter", consequence: "Slowest, and the only way to be sure." },
      { label: "Changed chapters", consequence: "Fast. A chapter that never changed is never re-read." },
      { label: "The first and last", consequence: "Fastest. Misses a bad chapter in the middle." },
      { label: "A sample", consequence: "Quick, and says which chapters it read." },
    ],
  },
];

// A file the change adds whole: every line new, numbered from 1.
function added(code: string[]): Line[] {
  return code.map((line, i) => ({ old: null, new: i + 1, code: line }));
}

// PR #141 as the review desk draws it (prototype/review-desk.html's FILES).
const LIMITS: FileDiff = {
  path: "worker/analysis/limits.ts",
  lines: [
    { old: 3, new: 3, code: "export const ACX_LIMITS = {" },
    { old: 4, new: 4, code: "  rms: { min: -23, max: -18 }," },
    { old: null, new: 5, code: "  peak: { max: -3 }," },
    { old: 5, new: 6, code: "} as const;" },
  ],
};
const PEAK: FileDiff = {
  path: "worker/analysis/checks/peak.ts",
  lines: added([
    "import { ACX_LIMITS } from '../limits';",
    "import { explain } from '../explain';",
    "import type { ChapterAnalysis, CheckResult } from '../types';",
    "",
    "export function checkPeak(chapter: ChapterAnalysis): CheckResult {",
    "  const { peakDb, peakAt } = chapter;",
    "  const limit = ACX_LIMITS.peak.max;",
    "",
    "  if (peakDb <= limit) {",
    "    return { check: 'peak', status: 'pass', measured: peakDb, limit };",
    "  }",
    "",
    "  return {",
    "    check: 'peak',",
    "    status: 'fail',",
    "    measured: peakDb,",
    "    limit,",
    "    at: peakAt,",
    "    reason: explain.peak({ measured: peakDb, limit, at: peakAt }),",
    "  };",
    "}",
  ]),
};
const PEAK_TEST: FileDiff = {
  path: "worker/analysis/checks/peak.test.ts",
  lines: added([
    "import { describe, expect, it } from 'vitest';",
    "import { analyseFixture } from '../../test/fixtures';",
    "import { checkPeak } from './peak';",
    "",
    "describe('checkPeak', () => {",
    "  it('passes the clean fixture', async () => {",
    "    const result = checkPeak(await analyseFixture('clean'));",
    "    expect(result.status).toBe('pass');",
    "  });",
    "",
    "  it('flags the clipped fixture above -3 dB', async () => {",
    "    const result = checkPeak(await analyseFixture('clipped'));",
    "    expect(result.status).toBe('fail');",
    "    expect(result.measured).toBeGreaterThan(-3);",
    "  });",
    "",
    "  it('reports when the loudest peak happens', async () => {",
    "    const result = checkPeak(await analyseFixture('clipped'));",
    "    expect(result.at).toBeDefined();",
    "  });",
    "});",
  ]).map((line) =>
    line.new === 19
      ? {
          ...line,
          finding: {
            by: "/code-review · Spec axis",
            body: (
              <>
                Only checks that <code>at</code> exists. Assert the clipped fixture’s known peak time so
                story 4 is actually proven.
              </>
            ),
          },
        }
      : line,
  ),
};
const CHECK_LABEL: FileDiff = {
  path: "app/compliance/check-label.ts",
  lines: [
    { old: 1, new: null, code: "export type CheckName = 'loudness';" },
    { old: null, new: 1, code: "export type CheckName = 'loudness' | 'peak';" },
    { old: 2, new: 2, code: "" },
    { old: 3, new: 3, code: "export const CHECK_LABELS: Record<CheckName, string> = {" },
    { old: 4, new: 4, code: "  loudness: 'Loudness'," },
    { old: null, new: 5, code: "  peak: 'Peaks'," },
    { old: 5, new: 6, code: "};" },
  ],
};
// A line longer than its column, so it can be seen to wrap.
const EXPLAIN: FileDiff = {
  path: "worker/analysis/explain.ts",
  lines: [
    { old: 11, new: 11, code: "export const explain = {" },
    {
      old: 12,
      new: null,
      code: "  peak: ({ measured, limit }: Failure) => `Peaks reach ${measured} dB, above the ${limit} dB ACX allows.`,",
    },
    {
      old: null,
      new: 12,
      code: "  peak: ({ measured, limit, at }: Failure) => `Peaks reach ${measured} dB at ${timestamp(at)}, above the ${limit} dB ceiling ACX allows for any chapter.`,",
    },
    { old: 13, new: 13, code: "};" },
  ],
};

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

      <Section title="Needs you">
        <div className={styles.row} style={{ alignItems: "start" }}>
          <div className={styles.column}>
            {NEEDS.map((need) => (
              <Specimen key={need.kind} name={`desk-${need.kind}`}>
                <div style={{ width: 350 }}>
                  <QueueItem need={need} />
                </div>
              </Specimen>
            ))}
            <Specimen name="desk-selected">
              <div style={{ width: 350 }}>
                <QueueItem need={REVIEW} pressed />
              </div>
            </Specimen>
            <Specimen name="desk-resolved">
              <div style={{ width: 350 }}>
                <QueueItem need={QUESTION} resolved="Answered · the session resumed" />
              </div>
            </Specimen>
          </div>
          <div className={styles.column}>
            {NEEDS.map((need) => (
              <Specimen key={need.kind} name={`need-${need.kind}`}>
                <div style={{ width: 400 }}>
                  <NeedsList>
                    <NeedRow need={need} href={`#desk-${need.kind}`} />
                  </NeedsList>
                </div>
              </Specimen>
            ))}
          </div>
        </div>
      </Section>

      <Section title="Acceptance criteria">
        <Specimen name="criteria">
          <div style={{ width: 340 }}>
            <Criteria criteria={CRITERIA} />
          </div>
        </Specimen>
      </Section>

      <Section title="Question card">
        <div className={styles.row}>
          <Specimen name="question-1">
            <div style={{ width: 600 }}>
              <QuestionCard ticket={130} by="Claude Code · wt/credits · 09:18" questions={ASKED} />
            </div>
          </Specimen>
          <Specimen name="question-4">
            <div style={{ width: 600 }}>
              <QuestionCard ticket={131} by="Claude Code · wt/room-tone · 10:02" questions={ASKED_FOUR} />
            </div>
          </Specimen>
        </div>
      </Section>

      <Section title="Diff">
        <div className={styles.row}>
          <Specimen name="diff">
            <div style={{ width: 720 }}>
              <Diff files={[LIMITS, PEAK, PEAK_TEST, CHECK_LABEL]} />
            </div>
          </Specimen>
          <Specimen name="diff-changed">
            <div style={{ width: 720 }}>
              <Diff files={[CHECK_LABEL, LIMITS]} />
            </div>
          </Specimen>
          <Specimen name="diff-long-line">
            <div style={{ width: 420 }}>
              <Diff files={[EXPLAIN]} />
            </div>
          </Specimen>
        </div>
      </Section>
    </main>
  );
}
