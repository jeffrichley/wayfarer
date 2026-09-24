import { useState } from "react";
import { useShallow } from "zustand/react/shallow";

import type { Beat, Lane } from "./api";
import { Beats } from "./Beats";
import { clock, useNow } from "./clock";
import { Criteria } from "./Criteria";
import { Frame, Split } from "./Frame";
import { atWorkHref, ticketHref } from "./links";
import { QuestionCard } from "./Question";
import { RepoBar } from "./RepoBar";
import { command, useItems } from "./store";
import { Kicker } from "./Type";
import styles from "./AtWork.module.css";

// At work: every session running, or stopped to ask, as a lane; the selected one's
// story; and a rail with its criteria, its test rhythm and what it has changed
// (docs/screens/live-build.md). Everything shown is the server's (ADR-0004); the
// screen only chooses which lane is selected.

// The lane the address names, as `/at-work#<ticket>`.
function named(): number | null {
  const ticket = Number(window.location.hash.slice(1));
  return Number.isInteger(ticket) && ticket > 0 ? ticket : null;
}

export function AtWork() {
  const lanes = useItems(
    useShallow((items) =>
      Object.values(items)
        .filter((item): item is Lane => item.kind === "lane")
        .sort((a, b) => a.ticket.number - b.ticket.number),
    ),
  );
  const [chosen, choose] = useState(named);
  // A lane that has gone leaves the first one selected, so one always is.
  const lane = lanes.find((l) => l.ticket.number === chosen) ?? lanes[0];

  function select(ticket: number) {
    choose(ticket);
    // Replaced, not pushed: going back leaves At work rather than stepping lanes.
    window.history.replaceState(null, "", atWorkHref(ticket));
  }

  return (
    <Frame bar={<RepoBar />}>
      <Split
        left={{
          label: "Sessions",
          width: 300,
          children: <Lanes lanes={lanes} selected={lane?.ticket.number} onSelect={select} />,
        }}
        right={lane && { label: "Evidence", width: 330, children: <Rail lane={lane} /> }}
      >
        {lane ? (
          <Story key={lane.id} lane={lane} />
        ) : (
          <p className={styles.empty}>
            No agent is working. Arming an effort's cascade starts one on every takeable ticket.
          </p>
        )}
      </Split>
    </Frame>
  );
}

// One button per lane, keyed by its ticket, so a lane that changes is updated in
// place and a lane with focus keeps it (#56).
function Lanes({
  lanes,
  selected,
  onSelect,
}: {
  lanes: Lane[];
  selected: number | undefined;
  onSelect: (ticket: number) => void;
}) {
  const now = useNow();
  return (
    <div className={styles.lanes} data-piece="session-lanes">
      <Kicker>{`At work · ${lanes.length} ${lanes.length === 1 ? "session" : "sessions"}`}</Kicker>
      {lanes.map((lane) => {
        const asking = lane.question !== null;
        return (
          <button
            key={lane.id}
            type="button"
            className={styles.lane}
            aria-pressed={lane.ticket.number === selected}
            data-piece={`lane-${lane.ticket.number}`}
            onClick={() => onSelect(lane.ticket.number)}
          >
            <span className={`st ${asking ? "st-ask" : "st-building"} ${styles.st}`} aria-hidden="true" />
            <span className={styles.name}>{lane.ticket.title}</span>
            <span className={styles.meta}>{`${lane.branch} · ${asking ? "waiting on you" : going(lane, now)}`}</span>
            {lane.latest !== null && (
              <span className={asking ? `${styles.beat} ${styles.ask}` : styles.beat}>
                {asking ? `Asked you: ${lane.latest}` : lane.latest}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// How long its latest session has been going, to the minute.
function going(lane: Lane, now: Date): string {
  if (lane.started === null) {
    return "starting";
  }
  const minutes = Math.floor((now.getTime() - Date.parse(lane.started)) / 60_000);
  return minutes < 1 ? "just started" : `${minutes} min`;
}

const NO_BEATS: Beat[] = [];

// The selected lane's story: its head, its beats, and the question it stopped on.
function Story({ lane }: { lane: Lane }) {
  const now = useNow();
  // Every session the story is told from, as a resume carries on the one that asked.
  const beats = useItems(
    useShallow((items) =>
      lane.sessions.length === 0
        ? NO_BEATS
        : Object.values(items).filter(
            (item): item is Beat => item.kind === "beat" && lane.sessions.includes(item.session),
          ),
    ),
  );
  const { ticket, effort, question } = lane;
  return (
    <section className={styles.story} data-piece="session-story">
      <div className={styles.head}>
        <Kicker>{`/implement · Claude Code · ${lane.branch} · issue #${ticket.number}`}</Kicker>
        <h1>
          <a href={ticketHref(effort.number, ticket.number)}>{ticket.title}</a>
        </h1>
        <div className={styles.state}>
          {question !== null ? (
            <>
              <span className="st st-ask" aria-hidden="true" />
              <span>Waiting on you</span>
            </>
          ) : (
            <>
              <span className="st st-building" aria-hidden="true" />
              <span>
                {lane.started === null ? "Building" : `Building · started ${clock(lane.started)} · ${going(lane, now)}`}
              </span>
            </>
          )}
        </div>
      </div>
      <Beats beats={beats}>
        {question !== null && (
          <div className={styles.question}>
            <Kicker>Needs your answer to continue</Kicker>
            <QuestionCard
              ticket={ticket.number}
              by={`Claude Code · ${lane.branch}`}
              questions={question.questions.map((q) => ({
                text: q.question,
                options: q.options.map((o) => ({ label: o.label, consequence: o.description })),
              }))}
              // Taking the label off resumes the session (#42); what follows arrives
              // over the stream like any other change.
              onSend={async (answers) => (await command(`/api/tickets/${ticket.number}/answer`, { answers })).ok}
            />
          </div>
        )}
      </Beats>
    </section>
  );
}

// The rail beside the story: the ticket's criteria as written, one mark per test
// run in the order they ran, and what the session has changed.
function Rail({ lane }: { lane: Lane }) {
  const files = lane.changes;
  // The longest change sets the scale every file's bar is drawn to.
  const widest = Math.max(1, ...files.map((f) => f.added + f.removed));
  return (
    <div data-piece="session-evidence">
      <div className={styles.block} data-piece="criteria">
        <Kicker>{`Acceptance criteria · ${lane.criteria.length}`}</Kicker>
        {lane.criteria.length > 0 ? (
          <Criteria criteria={lane.criteria} />
        ) : (
          <p className="meta">The ticket lists none.</p>
        )}
      </div>
      <div className={styles.block} data-piece="rhythm">
        <Kicker>Test rhythm</Kicker>
        {lane.rhythm.length > 0 ? (
          <>
            <div className={styles.rhythm} role="list" aria-label={`${lane.rhythm.length} test runs`}>
              {lane.rhythm.map((mark, i) => (
                // Keyed by place: runs only ever add to the end.
                <span
                  key={i}
                  role="listitem"
                  className={`tr ${mark.passed ? "tr-green" : "tr-red"}`}
                  aria-label={mark.passed ? "Green" : "Red"}
                />
              ))}
            </div>
            <p className="meta">
              {`${lane.rhythm.length} ${lane.rhythm.length === 1 ? "run" : "runs"}`}
              {lane.last_green !== null && ` · last green ${clock(lane.last_green)}`}
            </p>
          </>
        ) : (
          <p className="meta">No test runs yet.</p>
        )}
      </div>
      <div className={styles.block} data-piece="changes">
        <Kicker>{`Changes on ${lane.branch}`}</Kicker>
        {files.length > 0 ? (
          <ul className={styles.files}>
            {files.map((file) => (
              <li key={file.path}>
                <span className={styles.path}>{file.path}</span>
                <span className={styles.num}>{`+${file.added}${file.removed ? ` −${file.removed}` : ""}`}</span>
                <span className={styles.bar} aria-hidden="true">
                  <span className={styles.add} style={{ width: `${(file.added / widest) * 100}%` }} />
                  {file.removed > 0 && (
                    <span className={styles.del} style={{ width: `${(file.removed / widest) * 100}%` }} />
                  )}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="meta">Nothing changed yet.</p>
        )}
      </div>
    </div>
  );
}
