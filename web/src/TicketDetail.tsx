import type { ReactNode } from "react";

import type { Effort, GraphCard, Mention, Neighbour, Ticket, TicketGraph } from "./api";
import { Button } from "./Button";
import { Criteria } from "./Criteria";
import type { Selection } from "./GraphCanvas";
import { atWorkHref, deskHref } from "./links";
import { Mark, State } from "./State";
import { type Step, Thread } from "./Thread";
import { LOOKS } from "./TicketCard";
import { Chip, Kicker, Named } from "./Type";
import styles from "./TicketDetail.module.css";

// The ticket graph's panel: whatever the canvas has selected
// (docs/screens/ticket-graph.md). A ticket shows what to build, its criteria as
// written, what blocks it and what it frees, and its thread; the start line lists
// what has landed. Nothing here starts work: arming the cascade is the screen's
// one action, so a ticket's block says where it stands and where to go for it.
export function TicketDetail({
  selected,
  graph,
  effort,
  ticket,
  onFollow,
}: {
  selected: Selection;
  graph: TicketGraph;
  effort: Effort;
  // The selected ticket as the stream holds it, once it does.
  ticket: Ticket | undefined;
  // Following a ticket it names: its card, or the start line once it has landed.
  onFollow: (selection: Exclude<Selection, null>) => void;
}) {
  if (selected === "start") {
    return <Landed landed={graph.landed} />;
  }
  const card = graph.cards.find((c) => c.ticket.number === selected);
  if (card === undefined || ticket === undefined) {
    return (
      <Block kicker="Nothing selected">
        <p className="meta">
          Select a ticket to see what to build, what it waits on and what it frees. Select the start line to list
          what has landed.
        </p>
      </Block>
    );
  }
  const { glyph, word } = LOOKS[card.state];
  const follow = (neighbour: Neighbour) =>
    onFollow(neighbour.state === "landed" ? "start" : neighbour.ticket.number);
  return (
    <>
      <div className={styles.head}>
        <div className={styles.chips}>
          <Chip>{`Issue #${ticket.number}`}</Chip>
          {ticket.labels.map((label) => (
            <Chip key={label}>{label}</Chip>
          ))}
        </div>
        <h2>{ticket.title}</h2>
        <div className={styles.state}>
          <State glyph={glyph}>{ticket.pull_request ? `${word} · PR #${ticket.pull_request.number}` : word}</State>
        </div>
      </div>
      <Standing card={card} ticket={ticket} />
      <Block kicker="What to build">
        {ticket.build === null ? (
          <p className="meta">Its ticket has no What to build.</p>
        ) : (
          <div className={styles.prose} data-piece="what-to-build">
            {ticket.build.split(/\n\s*\n/).map((paragraph, i) => (
              // Keyed by place: its paragraphs in order, and two may read alike.
              <p key={i}>{paragraph}</p>
            ))}
          </div>
        )}
      </Block>
      <Block kicker="Acceptance criteria">
        {ticket.criteria.length === 0 ? (
          <p className="meta">Its ticket lists none.</p>
        ) : (
          <Criteria criteria={ticket.criteria} label="Acceptance criteria" />
        )}
      </Block>
      <Block kicker="Blocked by">
        {card.blocked_by.length === 0 ? (
          <p className="meta">Nothing: it could start the moment the cascade is armed.</p>
        ) : (
          <Edges label="Blocked by" edges={card.blocked_by} onFollow={follow} />
        )}
        {card.unblocks.length > 0 && (
          <>
            <span className={`kicker ${styles.then}`}>Unblocks</span>
            <Edges label="Unblocks" edges={card.unblocks} onFollow={follow} />
          </>
        )}
      </Block>
      <Block kicker="Thread">
        <Thread steps={thread(effort, ticket)} />
      </Block>
    </>
  );
}

function Block({ kicker, children }: { kicker: string; children: ReactNode }) {
  return (
    <div className={styles.block}>
      <Kicker>{kicker}</Kicker>
      {children}
    </div>
  );
}

// Tickets one step away, each followed to its card by its name. An implied
// blocker is listed though it is not drawn, saying which blocker implies it.
function Edges({
  label,
  edges,
  onFollow,
}: {
  label: string;
  edges: (Neighbour & { via?: Mention | null })[];
  onFollow: (neighbour: Neighbour) => void;
}) {
  return (
    <ul className={styles.edges} aria-label={label}>
      {edges.map((edge) => (
        <li key={edge.ticket.number}>
          <Mark {...LOOKS[edge.state]} />
          <span>
            <button type="button" className={styles.link} onClick={() => onFollow(edge)}>
              {edge.ticket.title}
            </button>
            {edge.via && <span className="meta">{` · implied through ${edge.via.title}`}</span>}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Where the ticket stands, and where to go to move it on. No block here starts
// or queues work: that is the cascade's, and the spec cut Start and Queue an
// agent (#14).
function Standing({ card, ticket }: { card: GraphCard; ticket: Ticket }) {
  switch (card.state) {
    case "takeable":
      return (
        <Block kicker="On the frontier">
          <p className={styles.prose}>
            {card.at_cap
              ? "Every slot is taken: the cascade starts it when one frees."
              : "Nothing blocks it: an armed cascade starts it."}
          </p>
        </Block>
      );
    case "building":
      return (
        <Block kicker="In a session">
          <p className={styles.prose}>A session is building it now.</p>
          <Button variant="secondary" arrow href={atWorkHref(ticket.number)} piece="watch-session">
            Watch the session
          </Button>
        </Block>
      );
    case "asked":
      return (
        <Block kicker="Paused for you">
          <p className={styles.quote}>{ticket.question?.questions[0]?.question ?? "It stopped to ask you something."}</p>
          <Button variant="secondary" arrow href={deskHref(`ticket:${ticket.number}`)} piece="answer-question">
            Answer on the desk
          </Button>
        </Block>
      );
    case "held":
      return (
        <Block kicker="Held for you">
          <p className={styles.prose}>It is kept back until you decide.</p>
          <Button variant="secondary" arrow href={deskHref(`ticket:${ticket.number}`)} piece="decide-held">
            Decide on the desk
          </Button>
        </Block>
      );
    case "landing":
      return (
        <Block kicker="Landing">
          <p className={styles.prose}>
            {ticket.place_in_line === null
              ? "Its pull request is in the merge queue."
              : `Its pull request is ${ordinal(ticket.place_in_line)} in the merge queue.`}
          </p>
        </Block>
      );
    case "in_review":
      return (
        <Block kicker="In review">
          <p className={styles.prose}>Its pull request is open, and not yet landing.</p>
        </Block>
      );
    case "blocked":
      return (
        <Block kicker="Not yet">
          <p className={styles.prose}>
            {card.waiting_on.length === 0
              ? `${ticket.assignees.join(" and ")} took it by hand, so the cascade leaves it alone.`
              : `Reaches the frontier once ${names(card.waiting_on)} ${card.waiting_on.length === 1 ? "lands" : "land"}.`}
          </p>
        </Block>
      );
    default:
      return null;
  }
}

// What the start line holds once it is the course: every landed ticket, in the
// order it depended on.
function Landed({ landed }: { landed: Mention[] }) {
  return (
    <>
      <div className={styles.head}>
        <Kicker>{landed.length === 0 ? "The start line" : "The course so far"}</Kicker>
        <h2>
          {landed.length === 0
            ? "Nothing landed yet"
            : `${landed.length} ${landed.length === 1 ? "ticket" : "tickets"} landed`}
        </h2>
      </div>
      <Block kicker="Landed">
        {landed.length === 0 ? (
          <p className="meta">The course starts here. Each ticket that lands folds into it.</p>
        ) : (
          <ul className={styles.edges} aria-label="Landed">
            {landed.map((ticket) => (
              <li key={ticket.number}>
                <Mark {...LOOKS.landed} />
                <span>
                  <Named name={ticket.title} id={ticket.number} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </Block>
    </>
  );
}

// The ticket traced from its map to landing (CONTEXT.md): solid through what has
// happened, pending into what has not.
function thread(effort: Effort, ticket: Ticket): Step[] {
  const { state, pull_request: pull } = ticket;
  const done = { glyph: "done", word: "Done" } as const;
  const pending = { glyph: "pending", word: "Not reached yet" } as const;
  const past = state === "landed" || state === "landing" || state === "in_review";
  const session: Pick<Step, "glyph" | "word" | "meta"> =
    state === "building"
      ? { glyph: "building", word: "Building", meta: "Running now" }
      : state === "asked"
        ? { glyph: "ask", word: "Asked", meta: "Asked you a question" }
        : state === "held"
          ? { glyph: "held", word: "Held", meta: "Held until you decide" }
          : past || pull !== null
            ? done
            : pending;
  return [
    effort.map === null
      ? { skill: "/wayfinder", name: "No map", ...pending }
      : { skill: "/wayfinder", name: <Named name={effort.map.title} id={effort.map.number} />, ...done },
    { skill: "/to-spec", name: <Named name={effort.title} id={effort.number} />, ...done },
    { skill: "/to-tickets", name: <Named name={ticket.title} id={ticket.number} />, ...done },
    { skill: "/tdd", name: session === pending ? "No session yet" : "A session", ...session },
    pull === null
      ? { skill: "/code-review", name: "No PR yet", ...pending }
      : {
          skill: "/code-review",
          name: `PR #${pull.number}`,
          ...(pull.merged ? done : { glyph: "review", word: "Open", meta: "Open" }),
        },
    state === "landed"
      ? { skill: "merge", name: "Landed", ...done }
      : state === "landing"
        ? { skill: "merge", name: "In the merge queue", glyph: "review", word: "Landing" }
        : { skill: "merge", name: "Not landed", ...pending },
  ];
}

function names(tickets: Mention[]): string {
  const quoted = tickets.map((t) => `“${t.title}”`);
  return quoted.length <= 2 ? quoted.join(" and ") : `${quoted.slice(0, -1).join(", ")} and ${quoted.at(-1)}`;
}

// "2nd", as the queue counts its line.
const PLACE = new Intl.PluralRules("en-GB", { type: "ordinal" });
const SUFFIX: Partial<Record<Intl.LDMLPluralRule, string>> = { one: "st", two: "nd", few: "rd" };

function ordinal(n: number): string {
  return `${n}${SUFFIX[PLACE.select(n)] ?? "th"}`;
}
