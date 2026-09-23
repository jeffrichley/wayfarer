import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";

import type { Beat, BeatKind } from "./api";
import styles from "./Beats.module.css";

// A reader this close to the bottom is following the story, and the pane keeps
// up with it; any further up and they are reading back, and it stays put. The
// prototype's distance (live-build.html), in pixels.
const NEAR_BOTTOM = 160;

// How often a call still in flight recounts its seconds.
const TICK_MS = 1000;

// Each kind's mark, and what it says to a person who cannot see it. Marks are
// shapes, never hues (docs/screens/live-build.md). An outcome has no mark in the
// prototype: its ringed dot is #49's, the session's end as a mark on a chart. A
// module's class is typed as possibly missing, as every index is here.
const MARKS: Record<BeatKind, [string | undefined, string]> = {
  read: [styles.read, "Read"],
  remark: [styles.remark, "Remark"],
  red: ["tr tr-red", "Failing test"],
  green: ["tr tr-green", "Passing test"],
  refactor: [styles.refactor, "Refactor"],
  outcome: [styles.outcome, "Outcome"],
  working: ["st st-building", "Working"],
};

// A session's story: its beats in the order they happened, grouped into the
// Orient before its first red and the numbered cycles after it (CONTEXT.md).
// The pane scrolls on its own, and follows new beats only while the reader is
// already at the bottom, so reading back is never pulled away.
export function Beats({ beats }: { beats: Beat[] }) {
  const pane = useRef<HTMLDivElement>(null);
  const following = useRef(true);
  const drawn = useRef(false);
  const lastTop = useRef(0);
  // The story as it stood when the pane opened is read, not watched arriving;
  // only what comes after rises into place.
  const [first] = useState(() => new Set(beats.map((beat) => beat.id)));

  // Whether the reader is at the bottom is read from where they leave the pane,
  // not after a beat has arrived, which a tall beat would decide for them.
  function near(at: HTMLDivElement): boolean {
    return at.scrollHeight - at.scrollTop - at.clientHeight < NEAR_BOTTOM;
  }

  // Only the reader scrolls up. The pane's own glide down can trail a burst of
  // beats by more than NEAR_BOTTOM, and must not read as the reader leaving.
  function scrolled() {
    const at = pane.current;
    if (at === null) {
      return;
    }
    if (near(at)) {
      following.current = true;
    } else if (at.scrollTop < lastTop.current) {
      following.current = false;
    }
    lastTop.current = at.scrollTop;
  }

  // Output opened in place moves the bottom away from a reader who has not moved.
  function toggled() {
    const at = pane.current;
    if (at !== null) {
      following.current = near(at);
    }
  }

  useLayoutEffect(() => {
    const at = pane.current;
    if (at !== null && following.current) {
      // The first drawing lands at the bottom at once; later beats glide in.
      at.scrollTo({ top: at.scrollHeight, behavior: drawn.current ? "smooth" : "instant" });
    }
    drawn.current = true;
  }, [beats]);

  const story = [...beats].sort((a, b) => a.seq - b.seq);
  return (
    <div ref={pane} className={`pane ${styles.pane}`} onScroll={scrolled}>
      <ol className={styles.beats} aria-live="polite">
        {story.flatMap((beat, i) => {
          const rows = [];
          if (beat.chapter !== story[i - 1]?.chapter) {
            rows.push(<Chapter key={`chapter:${beat.chapter}`} chapter={beat.chapter} />);
          }
          rows.push(
            beat.beat === "working" ? (
              <Working key={beat.id} beat={beat} />
            ) : (
              <Moment
                key={beat.id}
                beat={beat}
                arrived={!first.has(beat.id)}
                onToggle={toggled}
              />
            ),
          );
          return rows;
        })}
      </ol>
    </div>
  );
}

function Chapter({ chapter }: { chapter: number }) {
  return (
    <li className={styles.chap}>
      <span className={styles.label}>
        <span className="kicker">{chapter === 0 ? "Before any test" : "Red → green"}</span>
        {chapter === 0 ? "Orient" : `Cycle ${chapter}`}
      </span>
    </li>
  );
}

function Mark({ kind }: { kind: BeatKind }) {
  const [className, word] = MARKS[kind];
  return (
    <span className={styles.mk}>
      <span className={className} role="img" aria-label={word} />
    </span>
  );
}

// One beat: its time, its mark and its sentence, and a red's output folded
// beneath it, there when asked for and out of the way until then.
function Moment({
  beat,
  arrived,
  onToggle,
}: {
  beat: Beat;
  arrived: boolean;
  onToggle: () => void;
}) {
  const [open, setOpen] = useState(false);
  const output = useId();
  return (
    <li className={arrived ? `${styles.beat} ${styles.arrived}` : styles.beat}>
      <time dateTime={beat.at}>{clock(beat.at)}</time>
      <Mark kind={beat.beat} />
      <div className={styles.txt}>
        {beat.text}
        {beat.beat === "red" && beat.output && (
          <div>
            <button
              type="button"
              className={styles.toggle}
              aria-expanded={open}
              aria-controls={output}
              onClick={() => {
                // Opened in place, so the reader may no longer be at the bottom.
                flushSync(() => setOpen(!open));
                onToggle();
              }}
            >
              {open ? "Hide test output" : "Show test output"}
            </button>
            <pre id={output} className={styles.out} hidden={!open}>
              {beat.output}
            </pre>
          </div>
        )}
      </div>
    </li>
  );
}

// A call with no result yet, counting the time it has taken. Its beat replaces
// it at the same id when the result arrives.
function Working({ beat }: { beat: Beat }) {
  const now = useNow();
  return (
    <li className={styles.working}>
      <span />
      <Mark kind="working" />
      <span>
        {beat.text}
        {/* Recounted every second, which a screen reader need not hear. */}
        <span className="num" aria-live="off">
          {elapsed(now - Date.parse(beat.at))}
        </span>
      </span>
    </li>
  );
}

function useNow(): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, []);
  return now;
}

// The beat's time on the reader's own clock, as the prototype stamps it: 09:05.
function clock(at: string): string {
  const time = new Date(at);
  return [time.getHours(), time.getMinutes()].map((n) => String(n).padStart(2, "0")).join(":");
}

// 12s, 1m 17s, 1h 4m.
function elapsed(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(seconds / 60);
  if (minutes >= 60) {
    return `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  }
  return minutes > 0 ? `${minutes}m ${seconds % 60}s` : `${seconds}s`;
}
