import { type ReactNode, useEffect } from "react";

import type { DeskEntry, Home, Mention, Need, PullDiff, PullDiffUnreadable, Ticket } from "./api";
import { Button } from "./Button";
import styles from "./Desk.module.css";
import { Diff, type Line } from "./Diff";
import { ticketHref } from "./links";
import { holdsUpAndStarts, row, tickets } from "./NeedsYou";
import { QuestionCard } from "./Question";
import { State } from "./State";
import { command, useItems } from "./store";
import { Kicker, Named } from "./Type";

// The working surface for the item open on the desk: one built for each kind of
// decision, each with exactly one primary action, and what that action will do
// said before it (docs/screens/review-desk.md, principle 5). A resolved item says
// what happened, and offers nothing more.

function Head({
  kicker,
  name,
  facts,
  piece,
}: {
  kicker: string;
  name: ReactNode;
  facts?: ReactNode;
  piece: string;
}) {
  return (
    <header className={styles.head} data-piece={piece}>
      <Kicker>{kicker}</Kicker>
      <h2>{name}</h2>
      {facts && <div className={styles.facts}>{facts}</div>}
    </header>
  );
}

// A ticket's name, linking to its card on its effort's graph.
function named(ticket: Mention, effort: Mention) {
  return <Named name={ticket.title} id={ticket.number} href={ticketHref(effort.number, ticket.number)} />;
}

// Names joined as a sentence says them: "A", "A and B", "A, B and C".
function joined(names: ReactNode[]): ReactNode {
  return names.map((name, i) => (
    <span key={i}>
      {i === 0 ? "" : i === names.length - 1 ? " and " : ", "}
      {name}
    </span>
  ));
}

export function DeskItem({ entry }: { entry: DeskEntry }) {
  const repo = useItems((items) => (items["home"] as Home | undefined)?.repo ?? null);
  const need = entry.need;
  // An item on a ticket is keyed by the ticket's own id (wayfarer.desk).
  const ticket = useItems((items) => {
    const item = items[entry.key];
    return item?.kind === "ticket" ? item : undefined;
  });
  return (
    <div className={styles.inner}>
      <Surface need={need} ticket={ticket} repo={repo} resolved={entry.resolved} />
    </div>
  );
}

function Surface({
  need,
  ticket,
  repo,
  resolved,
}: {
  need: Need;
  ticket: Ticket | undefined;
  repo: string | null;
  resolved: string | null;
}) {
  const done = resolved !== null && (
    <p className={styles.resolved} data-piece="desk-resolved" role="status">
      <State glyph="done">{resolved}</State>
    </p>
  );
  switch (need.kind) {
    case "question": {
      const asking = ticket?.question ?? null;
      return (
        <>
          <Head
            piece="question-header"
            kicker={`Question · ${need.effort.title}`}
            name={named(need.ticket, need.effort)}
            facts={
              <>
                <State glyph="ask">Waiting on you</State>
                <span>{holdsUpAndStarts({ holdsUp: need.holds_up, starts: need.starts })}</span>
              </>
            }
          />
          {done || (
            <section className={styles.sec}>
              {asking === null || asking.answered ? (
                <p className={styles.prose}>
                  Its question comment is missing on GitHub, so it cannot be answered here. Answer it on
                  the ticket, and take the label off.
                </p>
              ) : (
                <div className={styles.panel}>
                  <QuestionCard
                    ticket={need.ticket.number}
                    by={`Claude Code · ${need.effort.title}`}
                    questions={asking.questions.map((q) => ({
                      text: q.question,
                      options: q.options.map((o) => ({ label: o.label, consequence: o.description })),
                    }))}
                    onSend={async (answers) =>
                      (await command(`/api/tickets/${need.ticket.number}/answer`, { answers })).ok
                    }
                  />
                </div>
              )}
            </section>
          )}
        </>
      );
    }
    case "held":
      return (
        <>
          <Head
            piece="held-header"
            kicker={`Held · ${need.effort.title}`}
            name={named(need.ticket, need.effort)}
            facts={
              <>
                <State glyph="held">Held</State>
                <span>{holdsUpAndStarts({ holdsUp: need.holds_up, starts: need.starts })}</span>
              </>
            }
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>{need.reason ?? "It is held until you decide."}</p>
              <p className={styles.consequence}>
                Continuing starts a session where the last one stopped. Starting over begins again from the
                effort branch, and closes its pull request.
                {ticket?.pull_request &&
                  " Letting it land takes its pull request as it is: ready, and into the merge queue."}
              </p>
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  piece="retry-continue"
                  onClick={() => void command(`/api/tickets/${need.ticket.number}/retry`, { start: "continue" })}
                >
                  Continue
                </Button>
                <Button
                  variant="secondary"
                  piece="retry-start-over"
                  onClick={() =>
                    void command(`/api/tickets/${need.ticket.number}/retry`, { start: "start_over" })
                  }
                >
                  Start over
                </Button>
                {ticket?.pull_request && (
                  <Button
                    variant="secondary"
                    piece="let-it-land"
                    onClick={() => void command(`/api/tickets/${need.ticket.number}/let-it-land`)}
                  >
                    Let it land
                  </Button>
                )}
              </div>
            </section>
          )}
        </>
      );
    case "review": {
      const pull = ticket?.pull_request ?? null;
      const starting = need.starting.map((t) => named(t, need.effort));
      // What it holds up, less itself and what starts at once, is still behind something.
      const waiting = need.holds_up - 1 - need.starting.length;
      return (
        <>
          <Head
            piece="pr-header"
            kicker={
              pull === null ? `In review · ${need.effort.title}` : `PR #${pull.number} · ${pull.branch} → ${pull.base}`
            }
            name={named(need.ticket, need.effort)}
            facts={
              <>
                <State glyph="review">In review</State>
                {/* A review is raised only for a pull request green or with no checks. */}
                <span>{pull?.checks === "passing" ? "Checks passed" : "No checks"}</span>
                <span>{holdsUpAndStarts({ holdsUp: need.holds_up, starts: need.starts })}</span>
              </>
            }
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>Clean and green, waiting on your approval.</p>
              <p className={styles.consequence} data-piece="lands">
                Landing it lands <b>{need.ticket.title}</b>.{" "}
                {starting.length === 0 ? (
                  "Nothing else starts the moment it does."
                ) : (
                  <>
                    {joined(starting)} {starting.length === 1 ? "starts" : "start"} the moment it does.
                  </>
                )}
                {waiting > 0 && ` ${tickets(waiting)} further on still ${waiting === 1 ? "waits" : "wait"}.`}
              </p>
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  piece="land-it"
                  onClick={() => void command(`/api/tickets/${need.ticket.number}/land-it`)}
                >
                  Land it
                </Button>
                {pull !== null && repo !== null && (
                  <Button variant="ghost" arrow piece="open-pull-request" href={`https://github.com/${repo}/pull/${pull.number}`}>
                    Open it on GitHub
                  </Button>
                )}
              </div>
            </section>
          )}
          {done || (pull !== null && <Changes pull={pull.number} head={pull.head_commit} />)}
        </>
      );
    }
    case "environment":
      return (
        <>
          <Head
            piece="environment-header"
            kicker="Environment · Every effort"
            name="Every cascade is paused"
            facts={<State glyph="blocked">Paused</State>}
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>{need.reason}</p>
              <ul className={styles.checks}>
                {need.failed.map((check) => (
                  <li key={check.name}>
                    <State glyph="blocked">{check.name}</State>
                    <p className="meta">{check.detail}</p>
                  </li>
                ))}
              </ul>
              <p className={styles.consequence}>
                Once it is fixed, resuming checks the environment again and starts what every paused cascade
                can. A cascade you paused yourself stays paused.
              </p>
              <div className={styles.actions}>
                <Button variant="primary" piece="resume-cascades" onClick={() => void command("/api/cascades/resume")}>
                  Resume the cascades
                </Button>
              </div>
            </section>
          )}
        </>
      );
    case "ship":
      return (
        <>
          <Head
            piece="ship-header"
            kicker={`Ship the effort · ${need.title}`}
            name={need.title}
            facts={<State glyph="take">Ready to ship</State>}
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>Every ticket landed on {need.branch}.</p>
              <p className={styles.consequence}>
                Shipping it is one review: its pull request from {need.branch} into {need.trunk}, where the
                repo&apos;s own checks apply.
              </p>
              {repo !== null && (
                <div className={styles.actions}>
                  <Button
                    variant="primary"
                    arrow
                    piece="open-effort-pull-request"
                    href={`https://github.com/${repo}/compare/${need.trunk}...${need.branch}?expand=1`}
                  >
                    Open its pull request
                  </Button>
                </div>
              )}
            </section>
          )}
        </>
      );
    case "orphan": {
      const said = row(need);
      const title = "ticket" in said ? said.ticket.name : "";
      const name =
        need.effort === null ? (
          <Named name={title} id={need.ticket} />
        ) : (
          named({ number: need.ticket, title }, need.effort)
        );
      return (
        <>
          <Head
            piece="orphan-header"
            kicker={`Leftover container · ${"effort" in said ? said.effort : ""}`}
            name={name}
            facts={<State glyph="ask">Left over</State>}
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>
                The Wayfarer running its session stopped before the session finished, and its container may
                still be running.
              </p>
              <p className={styles.consequence}>
                Reaping removes whatever it left running, and holds the ticket. Its work is not recovered.
              </p>
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  piece="reap"
                  onClick={() => void command(`/api/sessions/${encodeURIComponent(need.run_id)}/reap`)}
                >
                  Reap it
                </Button>
              </div>
            </section>
          )}
        </>
      );
    }
    case "closed":
      return (
        <>
          <Head
            piece="closed-header"
            kicker={`Closed with a live session · ${need.effort.title}`}
            name={named(need.ticket, need.effort)}
            facts={<State glyph="building">Still running</State>}
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>
                GitHub closed this ticket while its session runs. GitHub owns the ticket, so Wayfarer leaves the
                session alone.
              </p>
              <p className={styles.consequence}>Stopping it keeps its work, and holds the ticket.</p>
              <div className={styles.actions}>
                <Button
                  variant="primary"
                  piece="stop-session"
                  onClick={() => void command(`/api/tickets/${need.ticket.number}/stop`)}
                >
                  Stop its session
                </Button>
              </div>
            </section>
          )}
        </>
      );
    case "unknown_container":
      // Its label carries no repo, so it may be another repo's Wayfarer's: nothing
      // here reaps it (#43), and the person decides outside Wayfarer.
      return (
        <>
          <Head
            piece="unknown-header"
            kicker="Unknown container · No effort"
            name={`A container from run ${need.run_id}`}
            facts={<State glyph="building">Unknown</State>}
          />
          {done || (
            <section className={styles.sec}>
              <p className={styles.prose}>
                No session here accounts for it. It may belong to another repo&apos;s Wayfarer, so it is never
                removed from here. When you know it is not, remove it with Docker.
              </p>
            </section>
          )}
        </>
      );
  }
}

// The pull request's changes, read when the review opens and again as its head
// moves (#109). The page asks; the diff arrives on the stream.
function Changes({ pull, head }: { pull: number; head: string }) {
  useEffect(() => {
    void command(`/api/pulls/${pull}/read`);
  }, [pull, head]);
  const read = useItems((items) => items[`diff:${pull}`] as PullDiff | PullDiffUnreadable | undefined);
  let body: ReactNode;
  if (read === undefined) {
    body = <p className="meta">Reading its changes from GitHub.</p>;
  } else if (read.kind === "pull_diff_unreadable") {
    body = <p className={styles.prose}>{read.reason}</p>;
  } else {
    const [first, ...rest] = read.files.map((file) => ({
      path: file.path,
      // A line has an old number, a new one, or both; the server never sends neither.
      lines: file.lines as Line[],
    }));
    const unsent = read.left_out.length + read.unread;
    body = (
      <>
        {first === undefined ? (
          <p className={styles.prose}>It changes nothing that can be shown here.</p>
        ) : (
          <Diff files={[first, ...rest]} />
        )}
        {unsent > 0 && (
          <p className={styles.consequence}>
            {`${unsent} more changed ${unsent === 1 ? "file is" : "files are"} not shown here`}
            {read.left_out.length > 0 && `: ${read.left_out.map((file) => file.path).join(", ")}`}
            {read.unread > 0 && read.left_out.length > 0 && `, and ${read.unread} more`}.
          </p>
        )}
      </>
    );
  }
  return (
    <section className={`${styles.sec} ${styles.changes}`} data-piece="pr-diff">
      <Kicker>Changes</Kicker>
      {body}
    </section>
  );
}
