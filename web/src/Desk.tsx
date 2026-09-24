import { useEffect, useState } from "react";

import type { Desk as DeskItems, DeskEntry } from "./api";
import { RepoBar } from "./RepoBar";
import styles from "./Desk.module.css";
import { DeskItem } from "./DeskItem";
import { Frame, Split } from "./Frame";
import { deskHref } from "./links";
import { QueueItem, row } from "./NeedsYou";
import { useItems } from "./store";
import { useArrival } from "./visit";

// The review desk: everything waiting on the person, worked through in an order
// that holds still, with the chosen item's own working surface beside it
// (docs/screens/review-desk.md). The server freezes the order when the person
// arrives and re-ranks it when they come back (#57); the page only draws it.

const NOTHING: DeskEntry[] = [];

// The item a link opened, from `/desk#<key>`.
function linked(): string | null {
  const hash = decodeURIComponent(window.location.hash.slice(1));
  return hash === "" ? null : hash;
}

export function Desk() {
  useArrival("/api/desk/arrived");
  const entries = useItems((items) => (items["desk"] as DeskItems | undefined)?.entries ?? NOTHING);
  const [chosen, choose] = useState(linked);
  // Until one is chosen, or once the chosen one has gone on a re-rank, the first
  // item still waiting is open.
  const open =
    entries.find((entry) => entry.key === chosen) ??
    entries.find((entry) => entry.resolved === null) ??
    entries[0];

  useEffect(() => {
    // A newly opened item is read from its top.
    document.getElementById("desk-item")?.closest(".pane")?.scrollTo({ top: 0 });
  }, [open?.key]);

  function select(key: string) {
    choose(key);
    // The address names the item, so a reload or a shared link opens it; the
    // queue repaints in place, so focus stays on what was clicked.
    history.replaceState(null, "", deskHref(key));
  }

  const queue = (
    <div className={styles.queue} data-piece="needs-you-queue">
      <h1>Needs you</h1>
      <span className="meta">What holds up the most work, first.</span>
      {entries.length === 0 ? (
        <p className={styles.empty}>Nothing is waiting on you.</p>
      ) : (
        <div role="list">
          {entries.map((entry) => (
            <div role="listitem" key={entry.key} data-piece={`desk-${entry.key}`}>
              <QueueItem
                need={row(entry.need)}
                pressed={entry.key === open?.key}
                fresh={entry.new}
                resolved={entry.resolved ?? undefined}
                onSelect={() => select(entry.key)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <Frame bar={<RepoBar />}>
      <Split left={{ label: "Needs you", width: 350, children: queue }}>
        <section id="desk-item" className={styles.item} data-piece="desk-item">
          {open === undefined ? (
            <p className={styles.empty}>
              Nothing is waiting on you. Agents will stop here when they need a decision.
            </p>
          ) : (
            <DeskItem key={open.key} entry={open} />
          )}
        </section>
      </Split>
    </Frame>
  );
}
