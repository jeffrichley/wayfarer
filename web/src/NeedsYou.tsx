import type { ReactNode } from "react";

import styles from "./NeedsYou.module.css";
import { type Glyph, Mark } from "./State";
import { Named } from "./Type";

// One thing waiting on a person, of each kind this slice has
// (docs/design/data-and-commands.md, "Needs you"). What an item holds up is its
// ticket plus every open ticket downstream; `starts` is how many of those become
// takeable the moment it resolves. Both are counted elsewhere (#44) and only said
// here.
type OnATicket = { effort: string; ticket: { name: string; id: number } };
type HeldUp = { holdsUp: number; starts: number };
type HoldingUp = OnATicket & HeldUp;

export type Need =
  | { kind: "environment"; reason: string }
  | (HoldingUp & { kind: "question"; question: string })
  | (HoldingUp & { kind: "held"; reason: string })
  | (HoldingUp & { kind: "review" })
  | { kind: "drafts"; effort: string; spec: string; drafted: number }
  | { kind: "ship"; effort: string; name: string }
  | (OnATicket & { kind: "orphan" })
  | (OnATicket & { kind: "closed" });

// What a row says. The spec's one-line sentences lead with the reason or the
// question and end with what the item holds up; a row gives the item's name a
// line of its own, so the sentence under it calls the item "it".
type Words = {
  label: string;
  glyph: Glyph;
  word: string;
  name: ReactNode;
  ask: string;
  heldUp?: HeldUp;
};

const tickets = (n: number) => `${n} ${n === 1 ? "ticket" : "tickets"}`;

function words(need: Need): Words {
  const named = "ticket" in need && <Named name={need.ticket.name} id={need.ticket.id} />;
  const heldUp = "holdsUp" in need ? { holdsUp: need.holdsUp, starts: need.starts } : undefined;
  switch (need.kind) {
    case "environment":
      // It pauses every cascade in the repo, so it belongs to no one effort.
      return {
        label: "Environment · Every effort",
        glyph: "blocked",
        word: "Paused",
        name: "Every cascade is paused",
        ask: need.reason,
      };
    case "question":
      return {
        label: `Question · ${need.effort}`,
        glyph: "ask",
        word: "Asked",
        name: named,
        ask: need.question,
        heldUp,
      };
    case "held":
      return {
        label: `Held · ${need.effort}`,
        glyph: "held",
        word: "Held",
        name: named,
        ask: need.reason,
        heldUp,
      };
    case "review":
      return {
        label: `In review · ${need.effort}`,
        glyph: "review",
        word: "In review",
        name: named,
        ask: "Clean and green, waiting on your approval",
        heldUp,
      };
    case "drafts":
      return {
        label: `Drafts · ${need.effort}`,
        glyph: "ask",
        word: "Waiting on your check",
        name: need.spec,
        ask: `${tickets(need.drafted)} drafted, waiting on your check`,
      };
    case "ship":
      return {
        label: `Ship the effort · ${need.effort}`,
        glyph: "take",
        word: "Ready to ship",
        name: need.name,
        ask: "Every ticket landed · one review to ship it",
      };
    case "orphan":
      return {
        label: `Leftover container · ${need.effort}`,
        // The diamond is anything in Needs you waiting on a person's answer
        // (docs/design/visual-language.md); here, whether to reap it.
        glyph: "ask",
        word: "Left over",
        name: named,
        ask: "Its container outlived its session",
      };
    case "closed":
      return {
        label: `Closed with a live session · ${need.effort}`,
        glyph: "building",
        word: "Still running",
        name: named,
        ask: "Closed on GitHub while its session runs",
      };
  }
}

// "Holds up", never "unblocks": resolving a Held ticket may start nothing yet
// while still freeing everything behind it. The second half goes when it would
// say zero.
const holdsUp = (n: number) => `Holds up ${tickets(n)}`;

function holdsUpAndStarts({ holdsUp: n, starts }: HeldUp): string {
  return starts === 0 ? holdsUp(n) : `${holdsUp(n)} · ${starts} ${starts === 1 ? "starts" : "start"} the moment it lands`;
}

// Home's list of what needs you, in live order; each row goes to its item.
export function NeedsList({ children }: { children: ReactNode }) {
  return <ul className={styles.list}>{children}</ul>;
}

// A row of home's list. It says only how many tickets the item holds up, on the
// right (docs/screens/the-line.md); the desk says what starts.
export function NeedRow({ need, href }: { need: Need; href: string }) {
  const says = words(need);
  return (
    <li>
      <a className={styles.need} href={href}>
        <Mark glyph={says.glyph} word={says.word} />
        <span>
          <span className={styles.kind}>{says.label}</span>
          <span className={styles.name}>{says.name}</span>
          <span className={styles.ask}>{says.ask}</span>
        </span>
        {says.heldUp && <span className={styles.holds}>{holdsUp(says.heldUp.holdsUp)}</span>}
      </a>
    </li>
  );
}

// An item in the desk's queue: a button that opens it beside the queue. Once
// resolved it stays where it was, dimmed, and says what happened in place of what
// it held up, so the person's place in the queue never jumps
// (docs/screens/review-desk.md).
export function QueueItem({
  need,
  pressed = false,
  resolved,
  onSelect,
}: {
  need: Need;
  pressed?: boolean;
  resolved?: string;
  onSelect?: () => void;
}) {
  const says = words(need);
  const closing = resolved ?? (says.heldUp && holdsUpAndStarts(says.heldUp));
  return (
    <button
      type="button"
      className={resolved === undefined ? styles.item : `${styles.item} ${styles.resolved}`}
      aria-pressed={pressed}
      onClick={onSelect}
    >
      {resolved === undefined ? <Mark glyph={says.glyph} word={says.word} /> : <Mark glyph="done" word="Resolved" />}
      <span className={styles.itemKind}>{says.label}</span>
      <span className={styles.itemName}>{says.name}</span>
      <span className={styles.itemAsk}>{says.ask}</span>
      {closing && <span className={styles.itemHolds}>{closing}</span>}
    </button>
  );
}
