import type { ReactNode } from "react";

import { type Glyph, Run, State } from "../State";
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
];

function Specimen({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className={styles.specimen} data-specimen={name}>
      {children}
    </div>
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
            <Run passed={false}>Failing</Run>
          </Specimen>
          <Specimen name="run-green">
            <Run passed>Passing</Run>
          </Specimen>
        </div>
      </Section>

      <Section title="Type">
        <div className={styles.row}>
          <Specimen name="type-kicker">
            <span className="kicker">/to-tickets · 9 tracer bullets</span>
          </Specimen>
          <Specimen name="type-display">
            <h2>Pre-delivery compliance checks</h2>
          </Specimen>
          <Specimen name="type-body">
            <p>A ticket reaches the frontier when every ticket feeding into it has landed.</p>
          </Specimen>
          <Specimen name="type-meta">
            <span className="meta">Holds up 4 tickets · 1 starts the moment it lands</span>
          </Specimen>
          <Specimen name="type-name">
            <a className="nm" href="#127">
              Warn when no retail sample is chosen
            </a>
            <span className="id">#127</span>
          </Specimen>
          <Specimen name="type-skill">
            <span className="skill">/code-review</span>
          </Specimen>
          <Specimen name="type-chip">
            <span className="chip">AFK</span>
          </Specimen>
          <Specimen name="type-num">
            <span className="num">10:20</span>
          </Specimen>
        </div>
      </Section>

      <Section title="Buttons">
        <div className={styles.row}>
          <Specimen name="button-primary">
            <button type="button" className="btn btn-primary">
              Arm the cascade
            </button>
          </Specimen>
          <Specimen name="button-primary-disabled">
            <button type="button" className="btn btn-primary" aria-disabled="true">
              Arm the cascade
            </button>
          </Specimen>
          <Specimen name="button-secondary">
            <button type="button" className="btn btn-secondary">
              Review PR #141
            </button>
          </Specimen>
          <Specimen name="button-secondary-arrow">
            <button type="button" className="btn btn-secondary btn-arrow">
              Watch the session
            </button>
          </Specimen>
          <Specimen name="button-secondary-small">
            <button type="button" className="btn btn-secondary btn-sm">
              Start an agent
            </button>
          </Specimen>
          <Specimen name="button-ghost">
            <button type="button" className="btn btn-ghost">
              Queue an agent for when it unblocks
            </button>
          </Specimen>
        </div>
      </Section>
    </main>
  );
}
