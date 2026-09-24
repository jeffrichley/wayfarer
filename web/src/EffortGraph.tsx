import { useCallback, useEffect, useRef, useState } from "react";

import type { Cascade, Effort, Tally, Ticket, TicketGraph } from "./api";
import { Arming } from "./Arming";
import { Frame, Split } from "./Frame";
import { GraphCanvas, type Selection } from "./GraphCanvas";
import { ShellBar } from "./ShellBar";
import { State } from "./State";
import { command, connect, useItems } from "./store";
import { LOOKS } from "./TicketCard";
import { TicketDetail } from "./TicketDetail";
import styles from "./EffortGraph.module.css";

// The ticket graph: what is left and what is next (docs/screens/ticket-graph.md).
// The head names the effort and tallies where every ticket stands, the canvas
// draws what is still to land, and the panel shows whatever is selected. Its one
// action is arming the cascade (#55).

// A ticket's link opens it here, selected (links.ts): the hash names it.
function fromHash(): Selection {
  const n = Number(window.location.hash.slice(1));
  return Number.isInteger(n) && n > 0 ? n : null;
}

export function EffortGraph({ effort: number }: { effort: number }) {
  useEffect(connect, []);
  // A screen that shows an effort asks for it to be read (ADR-0003).
  useEffect(() => {
    void command(`/api/efforts/${number}/read`);
  }, [number]);
  const graph = useItems((items) => items[`graph:${number}`] as TicketGraph | undefined);
  const effort = useItems((items) => items[`effort:${number}`] as Effort | undefined);
  const cascade = useItems((items) => items[`cascade:${number}`] as Cascade | undefined);
  const [selected, setSelected] = useState<Selection>(fromHash);
  const ticket = useItems((items) =>
    typeof selected === "number" ? (items[`ticket:${selected}`] as Ticket | undefined) : undefined,
  );
  const canvas = useRef<HTMLDivElement>(null);

  const select = useCallback((selection: Selection) => {
    setSelected(selection);
    const { pathname, search } = window.location;
    history.replaceState(null, "", typeof selection === "number" ? `#${selection}` : pathname + search);
  }, []);

  // Following a ticket the panel names moves the selection to its card, and focus
  // with it, as the prototype's panel links do.
  const follow = (selection: Exclude<Selection, null>) => {
    select(selection);
    const piece = selection === "start" ? "start-line" : `ticket-card-${selection}`;
    canvas.current?.querySelector<HTMLElement>(`[data-piece="${piece}"]`)?.focus();
  };

  return (
    <Frame bar={<ShellBar />}>
      <Split
        right={{
          label: "The selected ticket",
          width: 400,
          children: graph && effort && (
            <div data-piece="ticket-detail" aria-live="polite">
              <TicketDetail selected={selected} graph={graph} effort={effort} ticket={ticket} onFollow={follow} />
            </div>
          ),
        }}
      >
        <section className={styles.column} data-piece="ticket-graph">
          {effort && (
            <div className={styles.head}>
              <div>
                <span className="kicker" data-piece="graph-kicker">
                  {`/to-tickets · ${effort.tickets.length} ${effort.tickets.length === 1 ? "ticket" : "tickets"} from spec #${effort.number}`}
                </span>
                <h1>{effort.title}</h1>
                <p className="meta">
                  Read left to right. A ticket reaches the frontier when every ticket feeding into it has landed.
                </p>
              </div>
              <div className={styles.side}>
                {graph && <Tallied tally={graph.tally} />}
                {cascade && <Arming cascade={cascade} />}
              </div>
            </div>
          )}
          <div ref={canvas} className={styles.canvas}>
            {graph !== undefined && <GraphCanvas graph={graph} selected={selected} onSelect={select} />}
          </div>
        </section>
      </Split>
    </Frame>
  );
}

// Where every ticket stands, a glyph and a count per state, as the server counts
// them.
function Tallied({ tally }: { tally: Tally[] }) {
  return (
    <ul className={styles.tally} aria-label="Ticket states">
      {tally.map(({ state, count }) => (
        <li key={state}>
          <State glyph={LOOKS[state].glyph}>{`${count} ${LOOKS[state].word.toLowerCase()}`}</State>
        </li>
      ))}
    </ul>
  );
}
