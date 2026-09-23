import { type Need, NeedRow, NeedsList, QueueItem } from "./NeedsYou";
import { layout, Section, Specimen } from "./gallery/Section";

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

export default function NeedsYouGallery() {
  return (
    <Section title="Needs you">
      <div className={layout.row} style={{ alignItems: "start" }}>
        <div className={layout.column}>
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
        <div className={layout.column}>
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
  );
}
