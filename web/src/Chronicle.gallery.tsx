import { useState } from "react";

import type { ChronicleLine, Mention } from "./api";
import { Chronicle, Line as ChronicleEntry } from "./Chronicle";
import { Section, Specimen } from "./gallery/Section";
import styles from "./Chronicle.gallery.module.css";

// The chronicle's sample effort and tickets, from the prototype's ACX effort.
const COMPLIANCE_CHECKS: Mention = { number: 124, title: "Pre-delivery compliance checks" };
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
  return { kind: "chronicle_line", id, at, effort: COMPLIANCE_CHECKS, moved };
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

export default function ChronicleGallery() {
  return (
    <>
      <Section title="Chronicle lines">
        <div className={styles.lines}>
          {LINES.map((l) => (
            <Specimen key={l.id} name={l.id}>
              <ol className={styles.chronicle}>
                <ChronicleEntry line={l} />
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
    </>
  );
}
