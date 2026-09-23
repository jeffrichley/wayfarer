import type { ReactNode } from "react";

import { Button, type ButtonProps } from "../Button";
import { Criteria } from "../Criteria";
import { Frame, Pane, Split } from "../Frame";
import { Route, type RouteProps } from "../Route";
import { type Glyph, State, TestRun, TestRuns } from "../State";
import { type Step, Thread } from "../Thread";
import { EffortItems, Menu, RepoItems, TopBar, type TopBarProps } from "../TopBar";
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

// The shell as the prototype draws it on galley, the sample repo.
const REPOS: TopBarProps["repos"] = [
  { name: "galley", meta: "3 efforts on the line", href: "#galley", current: true },
  { name: "madrigal", meta: "Connected today · no maps yet", href: "#madrigal" },
];
const EFFORT: NonNullable<TopBarProps["effort"]> = {
  name: "ACX compliance before delivery",
  efforts: [
    {
      name: "ACX compliance before delivery",
      meta: "Building · 2 of 9 landed · 2 building",
      glyph: "building",
      href: "#acx",
      current: true,
    },
    {
      name: "Per-chapter voice casting",
      meta: "Charting the way · 3 decided, 3 patches of fog",
      glyph: "building",
      href: "#casting",
    },
    {
      name: "Choosing the retail sample",
      meta: "Charting the way · one ticket left, in session with you",
      glyph: "ask",
      href: "#sample",
    },
  ],
  landed: [{ name: "Manuscript upload states", meta: "Landed 2 Sep · 6 tickets" }],
};
const BAR: TopBarProps = {
  repo: "galley",
  repos: REPOS,
  working: { count: 3, href: "#build" },
  needsYou: { count: 4, href: "#desk" },
};

// Where an effort is on the line: mid-build with two landed, sliced and waiting
// to be built, and still charting the way.
const ROUTES: [string, RouteProps][] = [
  [
    "route-building",
    {
      reached: "landed",
      current: "build",
      stations: {
        wayfinder: { glyph: "done", out: "7 decisions", href: "#map" },
        spec: { glyph: "done", out: "16 stories · 2 without a ticket", href: "#spec" },
        tickets: { glyph: "done", out: "9 tickets · 1 takeable", href: "#tickets" },
        build: { glyph: "ask", out: "2 building · 1 asking", href: "#build" },
        review: { glyph: "review", out: "1 PR waiting on you", href: "#desk" },
        landed: {
          glyph: "flag",
          out: "2 of 9",
          dots: [true, true, false, false, false, false, false, false, false],
        },
      },
    },
  ],
  [
    "route-sliced",
    {
      reached: "tickets",
      current: "tickets",
      stations: {
        wayfinder: { glyph: "done", out: "6 decisions · way clear", href: "#map" },
        spec: { glyph: "done", out: "Spec #168 · 12 stories", href: "#spec" },
        tickets: { glyph: "take", out: "5 tickets · 2 takeable", href: "#tickets" },
        build: { glyph: "pending", out: "—", why: "Opens once a ticket is taken" },
        review: { glyph: "pending", out: "—", why: "Opens once a ticket has a PR" },
        landed: { glyph: "pending", out: "—" },
      },
    },
  ],
  [
    "route-charting",
    {
      reached: "wayfinder",
      current: "wayfinder",
      stations: {
        wayfinder: { glyph: "building", out: "3 decided · 3 patches of fog", href: "#map" },
        spec: { glyph: "pending", out: "After the way is clear", why: "Opens once the map's way is clear" },
        tickets: { glyph: "pending", out: "—", why: "Opens once the map's way is clear" },
        build: { glyph: "pending", out: "—", why: "Opens once the map's way is clear" },
        review: { glyph: "pending", out: "—", why: "Opens once the map's way is clear" },
        landed: { glyph: "pending", out: "—" },
      },
    },
  ],
];

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

      <Section title="Top bar">
        <div className={styles.stack}>
          <Specimen name="topbar">
            <div className={styles.bar}>
              <TopBar {...BAR} />
            </div>
          </Specimen>
          <Specimen name="topbar-effort">
            <div className={styles.bar}>
              <TopBar {...BAR} effort={EFFORT} />
            </div>
          </Specimen>
          <Specimen name="topbar-nothing-waiting">
            <div className={styles.bar}>
              <TopBar {...BAR} effort={EFFORT} needsYou={{ count: 0, href: "#desk" }} />
            </div>
          </Specimen>
          <Specimen name="topbar-quiet">
            <div className={styles.bar}>
              <TopBar
                {...BAR}
                effort={EFFORT}
                working={{ count: 0, href: "#build" }}
                needsYou={{ count: 0, href: "#desk" }}
              />
            </div>
          </Specimen>
        </div>
        {/* Each switcher's menu, drawn open where it hangs beneath its button. */}
        <div className={styles.row}>
          <Specimen name="menu-repo">
            <div className={styles.menuBox}>
              <div className={styles.hang}>
                <Menu>
                  <RepoItems repos={REPOS} />
                </Menu>
              </div>
            </div>
          </Specimen>
          <Specimen name="menu-effort">
            <div className={styles.menuBox}>
              <div className={styles.hang}>
                <Menu wide>
                  <EffortItems efforts={EFFORT.efforts} landed={EFFORT.landed} />
                </Menu>
              </div>
            </div>
          </Specimen>
        </div>
      </Section>

      <Section title="Route band">
        <div className={styles.stack}>
          {ROUTES.map(([name, route]) => (
            <Specimen key={name} name={name}>
              <div className={styles.bar}>
                <Route {...route} />
              </div>
            </Specimen>
          ))}
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
