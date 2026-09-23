import type { ReactNode } from "react";

import type { Glyph } from "./State";

// One step of a ticket's thread: the skill that took it, what it made, and a
// line of meta. Its glyph says where the step stands: `done` has landed,
// `pending` has not happened yet, and any other glyph is the step happening now.
// The word says the same to a person who cannot see the glyph.
export type Step = {
  skill: string;
  name: ReactNode;
  meta?: string;
  glyph: Glyph;
  word: string;
};

// The thread: one ticket traced from its map through spec, ticket, session and
// pull request to landed (CONTEXT.md). The line runs solid through what has
// happened and dashed into what has not (docs/design/shell.md).
export function Thread({ steps }: { steps: Step[] }) {
  return (
    <ol className="thread">
      {steps.map((step, i) => {
        const pending = step.glyph === "pending";
        const nextPending = steps[i + 1]?.glyph === "pending";
        return (
          <li
            key={step.skill}
            className={[pending && "pending", nextPending && "next-pending"].filter(Boolean).join(" ")}
          >
            <span className="t-mark">
              <span className={`st st-${step.glyph}`} role="img" aria-label={step.word} />
            </span>
            <div>
              <span className="t-skill">{step.skill}</span>
              <div className="t-name">{step.name}</div>
              {step.meta && <div className="t-meta">{step.meta}</div>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
