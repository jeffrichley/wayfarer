import type { TicketState } from "./api";
import { type Glyph } from "./State";
import styles from "./TicketCard.module.css";

// The states a ticket graph draws a card in. A landed ticket has no card: it
// folds into the start line. A closed one is off the graph, and In review has no
// card in this slice (wayfarer#23).
export type CardState = Exclude<TicketState, "landed" | "closed" | "in_review">;

// What a card's foot needs to say the one fact that matters for its state
// (docs/screens/ticket-graph.md): how long a session has run, whether the slots
// are full, and which open tickets a blocked one waits on. Every other state's
// foot is fixed, so a state the model gains joins them until it says otherwise.
export type Doing =
  | { state: Exclude<CardState, "building" | "takeable" | "blocked"> }
  | { state: "building"; minutes: number }
  | { state: "takeable"; atCap: boolean }
  | { state: "blocked"; waitingOn: string[] };

const LOOKS: Record<CardState, { glyph: Glyph; word: string }> = {
  landing: { glyph: "review", word: "Landing" },
  building: { glyph: "building", word: "Building" },
  asked: { glyph: "ask", word: "Asked" },
  held: { glyph: "held", word: "Held" },
  takeable: { glyph: "take", word: "Takeable" },
  blocked: { glyph: "blocked", word: "Blocked" },
};

function foot(doing: Doing): string {
  switch (doing.state) {
    case "landing":
      return "In the merge queue";
    case "building":
      return `Working · ${doing.minutes} min`;
    case "asked":
      return "Asked you a question";
    case "held":
      return "Held · a blocking finding";
    case "takeable":
      return doing.atCap ? "Starts when a slot frees" : "Nobody on it yet";
    case "blocked":
      return doing.waitingOn.length === 1
        ? `Waiting on ${doing.waitingOn[0]}`
        : `Waiting on ${doing.waitingOn.length} tickets`;
  }
}

export type TicketCardProps = Doing & {
  name: string;
  number: number;
  // Full near the frontier, name-only further out; the graph's layout picks
  // (docs/screens/ticket-graph.md).
  size: "full" | "name-only";
  selected?: boolean;
  onSelect?: () => void;
};

// A ticket on the graph. The full card is its state word, its name and a foot
// that says what it is doing; the name-only card is its glyph, name and id.
// State is told by the edge's shape and tone, never by hue.
// A name is never cut off: it wraps, and a name longer than the card's clamp
// grows the card rather than losing its end (#48). The canvas places the card
// and the graph owns selection; the card only says whether it is selected.
export function TicketCard({ name, number, size, selected = false, onSelect, ...doing }: TicketCardProps) {
  const { glyph, word } = LOOKS[doing.state];
  const mark = <span className={`st st-${glyph}`} aria-hidden="true" />;
  return (
    <button
      type="button"
      className={`${styles.card} ${styles[size]} ${styles[doing.state]}`}
      aria-pressed={selected}
      aria-label={`${name}, ${word}`}
      onClick={onSelect}
    >
      {size === "full" ? (
        <>
          <span className={styles.top}>
            {mark}
            {word}
            <span className="id">{`#${number}`}</span>
          </span>
          <span className={styles.name}>{name}</span>
          <span className={styles.foot}>{foot(doing)}</span>
        </>
      ) : (
        <>
          {mark}
          <span className={styles.name}>
            {name} <span className="id">{`#${number}`}</span>
          </span>
        </>
      )}
    </button>
  );
}
