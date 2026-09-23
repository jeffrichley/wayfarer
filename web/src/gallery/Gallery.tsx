import type { ComponentType } from "react";

import styles from "./Gallery.module.css";
import { Section } from "./Section";

// Every primitive in every state, on one page. Each widget's specimens live
// beside it, in <Widget>.gallery.tsx, and are found here, so a ticket that lands
// a widget adds that file, and the same specimens drawn from the prototype's
// markup as a fragment in tests/prototype_gallery/, and edits neither page
// (#90). The snapshot check compares the two by name. The sections follow their
// files' names, so the page is the same every time.
const WIDGETS = Object.entries(
  import.meta.glob<{ default: ComponentType }>("../*.gallery.tsx", { eager: true }),
).sort(([a], [b]) => (a < b ? -1 : 1));

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

      {WIDGETS.map(([path, { default: Sections }]) => (
        <Sections key={path} />
      ))}
    </main>
  );
}
