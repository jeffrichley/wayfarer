import { Criteria } from "./Criteria";
import { Section, Specimen } from "./gallery/Section";

const CRITERIA = [
  "Measure the noise floor of every chapter",
  "Chapters above −60 dB fail the check",
  "Failures explain the value, the limit, and the timestamp",
  "The clean fixture passes",
];

export default function CriteriaGallery() {
  return (
    <Section title="Acceptance criteria">
      <Specimen name="criteria">
        <div style={{ width: 340 }}>
          <Criteria criteria={CRITERIA} />
        </div>
      </Specimen>
    </Section>
  );
}
