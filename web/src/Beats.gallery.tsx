import { useState } from "react";

import type { Beat, BeatKind } from "./api";
import { Beats } from "./Beats";
import { layout, Section, Specimen } from "./gallery/Section";
import styles from "./Beats.gallery.module.css";

// A beat of session `s` at 09:mm:ss on 15 September 2026, the reader's own
// clock, a little before the gallery's clock stands still in the tests.
function beat(
  seq: number,
  kind: BeatKind,
  [mm, ss]: [number, number],
  chapter: number,
  text: string,
  output: string | null = null,
): Beat {
  return {
    kind: "beat",
    id: `beat:s:${seq}`,
    session: "s",
    seq,
    beat: kind,
    at: new Date(2026, 8, 15, 9, mm, ss).toISOString(),
    chapter,
    text,
    run: null,
    output,
  };
}

// A finished session: an Orient, two cycles and the outcome that closed it,
// every kind of beat but a call in flight.
const STORY: Beat[] = [
  beat(1, "read", [5, 0], 0, "Read ISSUE.md, CONTEXT.md and beats.py"),
  beat(4, "remark", [8, 0], 0, "The analysis pass already runs astats, so the noise floor can join it."),
  beat(
    6,
    "red",
    [11, 0],
    1,
    "1 failing: measures the noise floor",
    "FAILED tests/test_noise_floor.py::test_measures_the_noise_floor\n  expected a noise floor, got None\n\n1 failed, 11 passed",
  ),
  beat(8, "green", [15, 0], 1, "12 passing"),
  beat(9, "refactor", [17, 0], 1, "Refactored limits.py; still 12 passing"),
  beat(12, "red", [19, 0], 2, "1 failing: flags the hiss fixture", "FAILED tests/test_noise_floor.py::test_flags_the_hiss_fixture"),
  beat(14, "green", [24, 0], 2, "13 passing"),
  beat(16, "outcome", [26, 0], 2, "Every criterion passes, and the full suite with them."),
];

// A session still going, with a call that has not answered yet. The call's seq
// is far past the rest, so beats the gallery adds sort in above it.
const LIVE: Beat[] = [
  beat(1, "read", [40, 0], 0, "Read ISSUE.md and CONTEXT.md"),
  beat(2, "remark", [41, 0], 0, "Running the suite before the first test."),
  beat(1000, "working", [41, 48], 0, "Running the full suite"),
];

// The live story, and a control beside it that adds a beat as a session would,
// so the pane can be seen to follow along or stay put.
function LiveBeats() {
  const [beats, setBeats] = useState(LIVE);
  const add = () => {
    const n = beats.length - LIVE.length + 1;
    const seq = LIVE.length - 1 + n; // after the live story's last beat, before the call
    setBeats([...beats, beat(seq, "remark", [41, 0], 0, `A later beat, number ${n}.`)]);
  };
  return (
    <div className={layout.row}>
      <Specimen name="beats-working">
        <div className={styles.story} style={{ height: 300 }}>
          <Beats beats={beats} />
        </div>
      </Specimen>
      <button type="button" className="btn btn-secondary btn-sm" onClick={add}>
        Add a beat
      </button>
    </div>
  );
}

export default function BeatsGallery() {
  return (
    <Section title="Beats">
      <div className={layout.row}>
        <Specimen name="beats">
          <div className={styles.story}>
            <Beats beats={STORY} />
          </div>
        </Specimen>
      </div>
      <LiveBeats />
    </Section>
  );
}
