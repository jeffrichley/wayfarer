import { type CSSProperties, type ReactNode, useState } from "react";

import type { LineRow, TicketState } from "./api";
import { atWorkHref, deskHref, effortHref } from "./links";
import { STATIONS, type StationKey } from "./Route";
import { SectionHead } from "./SectionHead";
import type { Glyph } from "./State";
import styles from "./Line.module.css";

// The line: every effort's route at once, one row each, its tickets at the
// stations they have reached (docs/screens/the-line.md). The server says which
// ticket is where; the row draws it, and says it in words.

const GLYPHS: Record<TicketState, Glyph> = {
  landed: "done",
  closed: "out",
  asked: "ask",
  held: "held",
  landing: "review",
  in_review: "review",
  building: "building",
  takeable: "take",
  blocked: "blocked",
};

// The legend: every glyph a row can draw, and what it means here.
const LEGEND: { glyph: Glyph; word: string }[] = [
  { glyph: "done", word: "Landed" },
  { glyph: "building", word: "Agent working" },
  { glyph: "ask", word: "Waiting on you" },
  { glyph: "review", word: "In review" },
  { glyph: "take", word: "Takeable" },
  { glyph: "blocked", word: "Blocked" },
];

// A caption's clauses: its words, and whether it waits on the person, which is
// set bold so it is found first.
type Clause = { words: string; you?: boolean };

function counted(states: TicketState[], state: TicketState): number {
  return states.filter((s) => s === state).length;
}

function clauses(row: LineRow, station: StationKey): Clause[] {
  const at = (key: "tickets" | "build" | "review") => row.stations[key];
  const says = (states: TicketState[], words: [TicketState, string, boolean?][]) =>
    words
      .map(([state, word, you]) => ({ n: counted(states, state), word, you }))
      .filter(({ n }) => n > 0)
      .map(({ n, word, you }) => ({ words: `${n} ${word}`, you }));
  switch (station) {
    case "tickets":
      return says(at("tickets"), [
        ["takeable", "takeable"],
        ["blocked", "blocked"],
      ]);
    case "build":
      return says(at("build"), [
        ["building", "building"],
        ["asked", "asking you", true],
        ["held", "held", true],
      ]);
    case "review":
      return says(at("review"), [
        ["in_review", "in review"],
        ["landing", "landing"],
      ]);
    case "landed":
      return [{ words: `${row.stations.landed.length} of ${row.total} landed` }];
    default:
      return [];
  }
}

// Where a station's cluster goes: the ticket graph for what is sliced and what
// has landed, At work for what is building, and the desk for what is in review.
function where(effort: number, station: StationKey): string {
  switch (station) {
    case "build":
      return atWorkHref();
    case "review":
      return deskHref();
    default:
      return effortHref(effort);
  }
}

function Caption({ says }: { says: Clause[] }) {
  return (
    <span className={styles.cap}>
      {says.map((clause, i) => (
        <span key={clause.words}>
          {i > 0 && " · "}
          {clause.you ? <strong>{clause.words}</strong> : clause.words}
        </span>
      ))}
    </span>
  );
}

// The tracks draw in once per browser session, never under reduced motion.
const INTRO = "wayfarer.intro.line";

function firstLook(): boolean {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return false;
  }
  try {
    const seen = sessionStorage.getItem(INTRO) !== null;
    sessionStorage.setItem(INTRO, "1");
    return !seen;
  } catch {
    return false; // storage blocked: no draw-in, rather than one on every visit
  }
}

export function Line({ rows }: { rows: LineRow[] }) {
  const [intro] = useState(firstLook);
  return (
    <section data-piece="the-line">
      <SectionHead title="The line" meta="Every ticket sits at the station it has reached.">
        <div className={styles.legend} aria-label="Legend">
          {LEGEND.map(({ glyph, word }) => (
            <span key={glyph}>
              <i className={`st st-${glyph}`} aria-hidden="true" />
              {word}
            </span>
          ))}
        </div>
      </SectionHead>
      <div className={`${styles.line}${intro ? ` ${styles.intro}` : ""}`}>
        <div className={styles.inner}>
          <div className={`${styles.row} ${styles.head}`}>
            <div className={styles.cell} />
            {STATIONS.map((station) => (
              <div key={station.key} className={styles.cell}>
                <span className={`${styles.skill} mono`}>{station.skill}</span>
                <span className={styles.sName}>{station.name}</span>
              </div>
            ))}
          </div>
          {rows.length === 0 && <p className={styles.empty}>No effort is on the line yet.</p>}
          {rows.map((row, place) => (
            <EffortRow key={row.id} row={row} place={place} />
          ))}
        </div>
      </div>
    </section>
  );
}

// One effort across the six stations. Its course is solid to the furthest
// station reached and dashed beyond; a finished effort's rests in ink.
function EffortRow({ row, place }: { row: LineRow; place: number }) {
  const furthest = STATIONS.findIndex((s) => s.key === row.reached);
  const effort = row.effort.number;
  return (
    <div
      className={`${styles.row}${row.done ? ` ${styles.done}` : ""}`}
      data-piece={`line-${effort}`}
    >
      <div className={styles.effort}>
        {row.done ? (
          <span className={styles.static}>{row.effort.title}</span>
        ) : (
          <a className={styles.name} href={effortHref(effort)}>
            {row.effort.title}
          </a>
        )}
        <span className="meta">
          Spec <span className="id">{`#${effort}`}</span>
          {row.done && " · landed"}
        </span>
      </div>
      {STATIONS.map((station, i) => {
        const states =
          station.key === "wayfinder" || station.key === "spec" ? [] : row.stations[station.key];
        const reached = i <= furthest;
        const says = clauses(row, station.key);
        let cluster: ReactNode;
        if (states.length > 0) {
          cluster = (
            <a
              className={styles.cluster}
              href={where(effort, station.key)}
              aria-label={`${station.name}: ${says.map((c) => c.words).join(", ")}`}
            >
              {states.map((state, n) => (
                // Keyed by place: a cluster is redrawn whole from the row.
                <i key={n} className={`st st-${GLYPHS[state]}`} aria-hidden="true" />
              ))}
            </a>
          );
        } else {
          // A station passed shows a filled point on the course; one ahead, a hollow one.
          cluster = (
            <span className={styles.cluster}>
              <i className={`${styles.passed}${reached ? "" : ` ${styles.ahead}`}`} />
            </span>
          );
        }
        const position = `${i === 0 ? ` ${styles.first}` : ""}${i === STATIONS.length - 1 ? ` ${styles.end}` : ""}`;
        return (
          <div
            key={station.key}
            className={`${styles.cell} ${styles.track}${reached ? "" : ` ${styles.pending}`}${position}`}
            style={{ "--d": `${place * 150 + i * 120}ms` } as CSSProperties}
            data-piece={`track-${station.key}`}
          >
            {cluster}
            {states.length > 0 && <Caption says={says} />}
          </div>
        );
      })}
    </div>
  );
}
