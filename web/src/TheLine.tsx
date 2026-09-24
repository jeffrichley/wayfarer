import { useEffect, useState } from "react";
import { useShallow } from "zustand/react/shallow";

import type { ChronicleLine, Home, LineRow, Need, NeedsYou } from "./api";
import { AppBar } from "./AppBar";
import { Button } from "./Button";
import { Chronicle } from "./Chronicle";
import { useNow } from "./clock";
import { Frame, Pane } from "./Frame";
import { Line } from "./Line";
import { atWorkHref, deskHref } from "./links";
import { NeedRow, NeedsList, row } from "./NeedsYou";
import { SectionHead } from "./SectionHead";
import { SessionImage } from "./SessionImage";
import { useItems } from "./store";
import { Kicker, Named } from "./Type";
import { useArrival } from "./visit";
import styles from "./TheLine.module.css";

// Home: what changed while the person was away, where everything is on the line,
// and what needs them and what is running (docs/screens/the-line.md). The only
// screen with no route band, since it shows every effort's route at once, and
// with no primary action, since the tracks already spend the accent.

// The visit the headline counts from ends when the person leaves home, and a new
// one begins when they arrive afresh (#58).
function useVisit() {
  useArrival("/api/home/arrived");
  useEffect(() => {
    // A beacon outlives the page it is sent from, which a fetch may not.
    const onHide = () => navigator.sendBeacon("/api/home/left");
    window.addEventListener("pagehide", onHide);
    return () => window.removeEventListener("pagehide", onHide);
  }, []);
}

const NOTHING: Need[] = [];

const DAY = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// Home shows today and yesterday, then earlier days one at a time (#22).
function shown(lines: ChronicleLine[], now: Date, earlier: number) {
  const dayOf = (at: string) => {
    const d = new Date(at);
    return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  };
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1).getTime();
  const before = [...new Set(lines.map((l) => dayOf(l.at)).filter((d) => d < yesterday))].sort(
    (a, b) => b - a,
  );
  const from = before[Math.min(earlier, before.length) - 1] ?? yesterday;
  return { lines: lines.filter((l) => dayOf(l.at) >= from), more: before.length > earlier };
}

function needKey(need: Need): string {
  switch (need.kind) {
    case "question":
    case "held":
    case "review":
    case "closed":
      return `ticket:${need.ticket.number}`;
    default:
      return need.id;
  }
}

export function TheLine() {
  useVisit();
  const now = useNow();
  const [earlier, setEarlier] = useState(0);
  const home = useItems((items) => items["home"] as Home | undefined);
  const needs = useItems((items) => (items["needs_you"] as NeedsYou | undefined)?.items ?? NOTHING);
  const rows = useItems(
    useShallow((items) =>
      Object.values(items)
        .filter((item): item is LineRow => item.kind === "line_row")
        .sort((a, b) => a.effort.number - b.effort.number),
    ),
  );
  const lines = useItems(
    useShallow((items) =>
      Object.values(items).filter((item): item is ChronicleLine => item.kind === "chronicle_line"),
    ),
  );
  const chronicle = shown(lines, now, earlier);
  const repo = home?.repo ?? "No GitHub repo";
  const moving = home?.moving ?? 0;
  const working = home?.working ?? [];

  return (
    <Frame bar={<AppBar />}>
      <Pane>
        <div className={styles.page}>
          <section className={styles.masthead} data-piece="masthead">
            <div>
              <Kicker>{`${repo} · the story so far`}</Kicker>
              <h1 data-piece="headline">{home?.headline}</h1>
              <p className={styles.lead} data-piece="standfirst">
                {home?.standfirst.join(" ")}
              </p>
            </div>
            <div className={styles.dateline}>
              <div className={styles.big}>{DAY.format(now).replace(",", "")}</div>
              <div className="meta num">
                {`${pad(now.getHours())}:${pad(now.getMinutes())} · ${moving} ${moving === 1 ? "effort" : "efforts"} moving`}
              </div>
            </div>
          </section>

          <Line rows={rows} />

          <div className={styles.lower}>
            <section data-piece="chronicle">
              <SectionHead title="The chronicle" meta="What happened, in order, by name." />
              <Chronicle
                lines={chronicle.lines}
                now={now}
                earlier={chronicle.more ? () => setEarlier((n) => n + 1) : undefined}
              />
            </section>

            <aside>
              <section data-piece="needs-you-panel">
                <SectionHead title="Needs you" meta="Most unblocking first" />
                {needs.length === 0 ? (
                  <p className={styles.empty}>
                    Nothing is waiting on you. Agents will stop here when they need a decision.
                  </p>
                ) : (
                  <>
                    <NeedsList>
                      {needs.map((need) => (
                        <NeedRow key={needKey(need)} need={row(need)} href={deskHref(needKey(need))} />
                      ))}
                    </NeedsList>
                    <div className={styles.foot}>
                      <span className="meta">Answers post back to the tracker as comments.</span>
                      <Button variant="secondary" arrow href={deskHref()} piece="open-desk">
                        Open the desk
                      </Button>
                    </div>
                  </>
                )}
              </section>

              <section className={styles.agents} data-piece="agents-at-work">
                <SectionHead title="At work" meta="Running right now" flush />
                {working.length === 0 ? (
                  <p className={styles.empty}>No agent is working.</p>
                ) : (
                  <ul>
                    {working.map(({ ticket, effort }) => (
                      <li key={ticket.number}>
                        <span className="st st-building" aria-hidden="true" />
                        <div>
                          <span className={styles.agent}>
                            <Named name={ticket.title} id={ticket.number} href={atWorkHref(ticket.number)} />
                          </span>
                          <span className="meta">{effort.title}</span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>

          <SessionImage />
        </div>
      </Pane>
    </Frame>
  );
}
