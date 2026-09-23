import styles from "./Route.module.css";
import { type Glyph } from "./State";

// The route band: the skill line, and the navigation. Moving between screens is
// moving along the line (docs/design/shell.md).
export const STATIONS = [
  { key: "wayfinder", skill: "/wayfinder", name: "Chart the way" },
  { key: "spec", skill: "/to-spec", name: "Write the spec" },
  { key: "tickets", skill: "/to-tickets", name: "Slice into tickets" },
  { key: "build", skill: "/tdd", name: "Build" },
  { key: "review", skill: "/code-review", name: "Review" },
  { key: "landed", skill: "merge", name: "Landed" },
] as const;

export type StationKey = (typeof STATIONS)[number]["key"];

// A station on the way: its glyph and its output line, and either the screen it
// links to or why it has none yet. A station with no screen is not a link.
export type Stop = { glyph: Glyph; out: string } & ({ href: string } | { why: string });

// The end of the line has no screen of its own: it shows a flag once anything
// has landed, and a dot per ticket, filled when that ticket landed.
export type End = { glyph: Glyph | "flag"; out: string; dots?: boolean[] };

export type RouteProps = {
  stations: Record<Exclude<StationKey, "landed">, Stop> & { landed: End };
  // The furthest station the work has reached: the course is solid up to it and
  // dashed beyond.
  reached: StationKey;
  // The station whose screen this is.
  current?: StationKey;
};

export function Route({ stations, reached, current }: RouteProps) {
  const furthest = STATIONS.findIndex((s) => s.key === reached);
  return (
    <nav className={styles.route} data-piece="route" aria-label="Where this effort is on the skill line">
      {STATIONS.map((station, i) => {
        const inner = (
          <>
            <span className={styles.skill}>{station.skill}</span>
            <span className={styles.node}>
              <Node glyph={stations[station.key].glyph} />
              <span
                className={`${styles.track}${i < furthest ? "" : ` ${styles.ahead}`}`}
                data-piece="track"
              />
            </span>
            <span className={styles.name}>{station.name}</span>
            <span className={styles.out}>
              {station.key === "landed" && <Dots dots={stations.landed.dots} />}
              {stations[station.key].out}
            </span>
          </>
        );
        const piece = `station-${station.key}`;
        if (station.key === "landed") {
          return (
            <div key={station.key} className={styles.station} data-piece={piece}>
              {inner}
            </div>
          );
        }
        const stop = stations[station.key];
        if ("href" in stop) {
          return (
            <a
              key={station.key}
              className={styles.station}
              href={stop.href}
              aria-current={current === station.key ? "page" : undefined}
              data-piece={piece}
            >
              {inner}
            </a>
          );
        }
        return (
          <div key={station.key} className={styles.station} aria-disabled="true" title={stop.why} data-piece={piece}>
            {inner}
          </div>
        );
      })}
    </nav>
  );
}

function Node({ glyph }: { glyph: Glyph | "flag" }) {
  if (glyph === "flag") {
    return <span className={styles.flag} aria-hidden="true" />;
  }
  return <span className={`st st-${glyph}`} aria-hidden="true" />;
}

// The output line carries the count in words; the dots only draw it.
function Dots({ dots }: { dots?: boolean[] }) {
  if (dots === undefined) {
    return null;
  }
  return (
    <span className={styles.dots} aria-hidden="true">
      {dots.map((on, i) => (
        // Keyed by place: a ticket's dot stays where it is.
        <i key={i} className={on ? styles.on : undefined} />
      ))}
    </span>
  );
}
