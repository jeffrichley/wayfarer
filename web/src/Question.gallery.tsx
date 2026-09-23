import { type Question, QuestionCard } from "./Question";
import { layout, Section, Specimen } from "./gallery/Section";

// #130's question, as the prototype asks it (WS.TICKETS in assets/wayfarer.js).
const ASKED: Question[] = [
  {
    text: "DOCX manuscripts don't mark front and back matter, so for those books I can only guess where credits would be. Should a DOCX book with no credits I can find fail like EPUB, or warn so the author can confirm?",
    options: [
      {
        label: "Fail, same as EPUB",
        consequence: "Stricter. Some DOCX books with real credits may fail until the author marks them.",
      },
      {
        label: "Warn, and ask the author to confirm",
        consequence: "Export stays unlocked for this check once they confirm credits are there.",
      },
    ],
  },
];

// As many questions as one ask carries, each with as many options as it can.
const ASKED_FOUR: Question[] = [
  {
    text: "Room tone at the head of a chapter can run long. Should more than one second fail the check, or only less than half a second?",
    options: [
      { label: "Both fail", consequence: "Matches ACX's wording. Some narrators' long heads will need trimming." },
      { label: "Only too little fails", consequence: "Long heads pass. A later check can warn about them." },
    ],
  },
  {
    text: "Where should a failing chapter say how much tone it found?",
    options: [
      { label: "In the check's line", consequence: "One place to read it, beside the pass or fail." },
      { label: "In the chapter's detail", consequence: "The check's line stays short; the number is a click away." },
      { label: "Both", consequence: "Repeats the number, so the two must stay in step." },
    ],
  },
  {
    text: "A chapter with no audio at all: does it fail room tone, or is that another check's job?",
    options: [
      { label: "Fail room tone", consequence: "The author sees one more failure for the same chapter." },
      { label: "Leave it to another check", consequence: "Room tone skips empty chapters and says so." },
    ],
  },
  {
    text: "Which chapters does the check read?",
    options: [
      { label: "Every chapter", consequence: "Slowest, and the only way to be sure." },
      { label: "Changed chapters", consequence: "Fast. A chapter that never changed is never re-read." },
      { label: "The first and last", consequence: "Fastest. Misses a bad chapter in the middle." },
      { label: "A sample", consequence: "Quick, and says which chapters it read." },
    ],
  },
];

export default function QuestionGallery() {
  return (
    <Section title="Question card">
      <div className={layout.row}>
        <Specimen name="question-1">
          <div style={{ width: 600 }}>
            <QuestionCard ticket={130} by="Claude Code · wt/credits · 09:18" questions={ASKED} />
          </div>
        </Specimen>
        <Specimen name="question-4">
          <div style={{ width: 600 }}>
            <QuestionCard ticket={131} by="Claude Code · wt/room-tone · 10:02" questions={ASKED_FOUR} />
          </div>
        </Specimen>
      </div>
    </Section>
  );
}
