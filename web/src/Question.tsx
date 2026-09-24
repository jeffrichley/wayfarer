import { useId, useState } from "react";

import { Button } from "./Button";

// One answer a session offers, and the sentence on what picking it means.
export type Option = { label: string; consequence: string };

// One thing a session asked. A session asks with `AskUserQuestion`, which carries
// one to four questions of two to four options each (docs/design/data-and-commands.md).
export type Question = { text: string; options: Option[] };

type Props = {
  ticket: number;
  // Who asked, from where and when: "Claude Code · wt/credits · 09:18".
  by: string;
  questions: Question[];
  // Posts the answer: one for each question, keyed by it, a choice and a note
  // together both said, the choice first. Whether it was taken.
  onSend?: (answers: Record<string, string>) => Promise<boolean>;
};

// What a session paused to ask, and where a person answers it (docs/design/shell.md,
// "Question card"). Sending needs a choice for every question, or a note; once
// sent, the controls lock and the card says the answer was posted to the ticket.
// Posting the answer is the screen's, through `onSend`.
export function QuestionCard({ ticket, by, questions, onSend }: Props) {
  const [choices, setChoices] = useState<(string | null)[]>(() => questions.map(() => null));
  const [note, setNote] = useState("");
  const [refused, setRefused] = useState(false);
  const [sent, setSent] = useState(false);
  const [lost, setLost] = useState(false);
  const noteId = useId();

  function pick(question: number, label: string) {
    if (sent) return;
    setChoices((picked) => picked.map((choice, i) => (i === question ? label : choice)));
  }

  async function send() {
    const answered = note.trim() !== "" || !choices.includes(null);
    setRefused(!answered);
    setLost(false);
    setSent(answered);
    if (!answered || onSend === undefined) return;
    const said = note.trim();
    const taken = await onSend(
      Object.fromEntries(
        questions.map((question, q) => [
          question.text,
          [choices[q], said].filter((part) => part !== null && part !== "").join("\n\n"),
        ]),
      ),
    );
    // Not taken, so nothing was posted: the controls open again to send it again.
    setSent(taken);
    setLost(!taken);
  }

  const each = questions.length > 1 ? " for each question" : "";
  const hint = sent
    ? `Posted to #${ticket}. The session resumes.`
    : lost
      ? "It was not posted. Send it again."
      : refused
      ? `Choose an option${each}, or write an answer first.`
      : "Pick an option or write your own answer.";

  return (
    <div className="qcard" data-piece={`question-${ticket}`}>
      {questions.map((question, q) => (
        // Keyed by place: a session's questions come in the order it asked them.
        <div key={q} className={q > 0 ? "q-next" : undefined}>
          <div className="convo">
            <div className="msg">
              <span className="who">AI</span>
              <div className="body">
                {q === 0 && <span className="by">{by}</span>}
                {question.text}
              </div>
            </div>
          </div>
          <div className="q-options" role="radiogroup" aria-label={question.text}>
            {question.options.map((option) => (
              <button
                key={option.label}
                type="button"
                className="choice"
                role="radio"
                aria-checked={choices[q] === option.label}
                aria-disabled={sent || undefined}
                tabIndex={sent ? -1 : undefined}
                onClick={() => pick(q, option.label)}
              >
                <span className="radio" />
                <span>
                  <span className="c-title">{option.label}</span>
                  <span className="c-sub">{option.consequence}</span>
                </span>
              </button>
            ))}
          </div>
        </div>
      ))}
      <div className="q-note">
        <label className="field-label" htmlFor={noteId}>
          Anything the agent should know
        </label>
        <textarea
          className="textarea"
          id={noteId}
          placeholder="Optional. The agent reads this before it resumes."
          value={note}
          readOnly={sent}
          onChange={(event) => setNote(event.target.value)}
        />
        <div className="q-send">
          <Button variant="primary" disabled={sent} piece={`send-answer-${ticket}`} onClick={() => void send()}>
            {sent ? "Answer sent" : "Send answer and resume"}
          </Button>
          <span className={`meta q-hint${sent || refused || lost ? " spoken" : ""}`} role="status">
            {hint}
          </span>
        </div>
      </div>
    </div>
  );
}
