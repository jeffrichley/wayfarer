import { Fragment, type ReactElement, type ReactNode } from "react";

import type { ChronicleLine, Mention, Someone } from "./api";
import { Button } from "./Button";
import { effortHref, ticketHref } from "./links";
import type { Glyph } from "./State";
import { Kicker, Named } from "./Type";
import styles from "./Chronicle.module.css";

// The chronicle: what moved the tickets, in sentences, by name (#22). The server
// derives each line and says only what moved; the sentence is written here, from
// one template per kind of movement, so a rebuilt chronicle reads the same and
// no line can misname a ticket. A line tells which tickets moved, never which
// skill was running, and carries its effort's name where the prototype put the
// skill.

type Moved = ChronicleLine["moved"];

// A line's glyph. The sentence carries the words, so the glyph is not read out.
const GLYPHS: Record<Moved["kind"], Glyph> = {
  taken: "building",
  asked: "ask",
  answered: "building",
  held: "held",
  retried: "building",
  landed: "done",
  closed: "out",
  armed: "building",
  published: "done",
  ready_to_ship: "review",
  shipped: "done",
};

const NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

function count(n: number): string {
  return NUMBERS[n] ?? String(n);
}

// A sentence is written as parts: its words, and the names in it. Adjacent words
// are joined into one text before it is drawn, because the browser shapes one
// text differently from the same words split across several.
type Part = string | ReactElement;

function joinWords(parts: Part[]): ReactNode {
  const joined: Part[] = [];
  for (const part of parts) {
    const last = joined.at(-1);
    if (typeof part === "string" && typeof last === "string") {
      joined[joined.length - 1] = last + part;
    } else {
      joined.push(part);
    }
  }
  // Keyed by place: a sentence is written once, whole.
  return joined.map((part, i) => <Fragment key={i}>{part}</Fragment>);
}

// "A", "A and B", "A, B, and C".
function listed(items: Part[]): Part[] {
  return items.flatMap((item, i) =>
    i === 0 ? [item] : [items.length === 2 ? " and " : i === items.length - 1 ? ", and " : ", ", item],
  );
}

// Who did it, for a kind a person can do: you, or anyone else by their login.
function who(by: "you" | Someone): string {
  return by === "you" ? "You" : by.login;
}

function sentence(line: ChronicleLine): Part[] {
  const effort = line.effort;
  const ticket = (mention: Mention) => (
    <Named name={mention.title} id={mention.number} href={ticketHref(effort.number, mention.number)} />
  );
  const theEffort = <Named name={effort.title} id={effort.number} href={effortHref(effort.number)} />;

  // What a landing, an arming or a publish directly caused: the tickets it made
  // takeable, and the sessions the cascade started on them (#22).
  const caused = (freed: Mention[], started: Mention[]): Part[] => {
    const agents = started.length === 1 ? "An agent" : "Agents";
    if (freed.length === 0) {
      // Only an arming starts sessions without freeing anything.
      return started.length === 0 ? [] : [` ${agents} took `, ...listed(started.map(ticket)), "."];
    }
    if (started.length === 0) {
      return [" ", ...listed(freed.map(ticket)), " reached the frontier."];
    }
    // Sessions start only on what the line freed, so when all of them started
    // they are named already.
    const them =
      started.length < freed.length
        ? listed(started.map(ticket))
        : [{ 1: "it", 2: "both" }[freed.length] ?? `all ${count(freed.length)}`];
    return [" ", ...listed(freed.map(ticket)), ` reached the frontier, and ${agents.toLowerCase()} took `, ...them, "."];
  };

  const moved = line.moved;
  switch (moved.kind) {
    case "taken":
      return moved.by === "wayfarer"
        ? [ticket(moved.ticket), " was taken."]
        : [`${who(moved.by)} took `, ticket(moved.ticket), "."];
    case "asked":
      return [ticket(moved.ticket), moved.gist === null ? " stopped to ask." : ` stopped to ask: “${moved.gist}”`];
    case "answered":
      return [`${who(moved.by)} answered `, ticket(moved.ticket), ", and its session resumed."];
    case "held":
      return [ticket(moved.ticket), moved.reason === null ? " was held." : ` was held. ${moved.reason}`];
    case "retried":
      return [
        "You retried ",
        ticket(moved.ticket),
        moved.over === null
          ? "."
          : moved.over
            ? ", starting over from the effort branch."
            : ", continuing where its session stopped.",
      ];
    case "landed":
      return [
        ...(moved.by === "wayfarer"
          ? [ticket(moved.ticket), " landed."]
          : [`${who(moved.by)} landed `, ticket(moved.ticket), " by hand, not re-tested."]),
        ...caused(moved.freed, moved.started),
      ];
    case "closed":
      return [`${who(moved.by)} closed `, ticket(moved.ticket), " without landing it."];
    case "armed":
      return ["You armed the cascade on ", theEffort, ".", ...caused([], moved.started)];
    case "published":
      return [
        theEffort,
        ` was sliced into ${count(moved.tickets)} ${moved.tickets === 1 ? "ticket" : "tickets"}.`,
        ...caused(moved.freed, moved.started),
      ];
    case "ready_to_ship":
      return [theEffort, " became ready to ship: its last ticket landed."];
    case "shipped":
      return [theEffort, " shipped."];
  }
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

// One line: its time, its glyph, its sentence, and its effort's name.
export function Line({ line }: { line: ChronicleLine }) {
  const at = new Date(line.at);
  const date = `${at.getFullYear()}-${pad(at.getMonth() + 1)}-${pad(at.getDate())}`;
  const time = `${pad(at.getHours())}:${pad(at.getMinutes())}`;
  return (
    <li className={styles.entry}>
      <time dateTime={`${date}T${time}`}>{time}</time>
      <span className={`st st-${GLYPHS[line.moved.kind]}`} aria-hidden="true" />
      <p>{joinWords(sentence(line))}</p>
      {/* The effort's name, in the place and look the prototype gave the skill (#22). */}
      <span className="skill">{line.effort.title}</span>
    </li>
  );
}

// A local day, as the lines on it are grouped.
function dayOf(at: Date): number {
  return new Date(at.getFullYear(), at.getMonth(), at.getDate()).getTime();
}

const LONG = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" });
const LONGER = new Intl.DateTimeFormat("en-GB", {
  weekday: "long",
  day: "numeric",
  month: "long",
  year: "numeric",
});

// A shipped effort's lines outlive the year they were written in (#22), so a day
// from another year says which.
function heading(day: number, now: Date): string {
  const today = dayOf(now);
  if (day === today) {
    return "Today";
  }
  const format = new Date(day).getFullYear() === now.getFullYear() ? LONG : LONGER;
  const date = format.format(day).replace(",", "");
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  return day === yesterday.getTime() ? `Yesterday · ${date}` : date;
}

// The lines under their days, newest first. Earlier days load one at a time:
// `earlier` asks for the next, and is absent when there is nothing before them.
export function Chronicle({
  lines,
  now,
  earlier,
}: {
  lines: ChronicleLine[];
  now: Date;
  earlier?: () => void;
}) {
  const days = new Map<number, ChronicleLine[]>();
  for (const line of [...lines].sort((a, b) => Date.parse(b.at) - Date.parse(a.at))) {
    const day = dayOf(new Date(line.at));
    days.set(day, [...(days.get(day) ?? []), line]);
  }
  return (
    <div>
      {[...days].map(([day, dayLines]) => (
        <div key={day} className={styles.day} data-day>
          <Kicker>{heading(day, now)}</Kicker>
          <ol>
            {dayLines.map((line) => (
              <Line key={line.id} line={line} />
            ))}
          </ol>
        </div>
      ))}
      {earlier && (
        <div className={styles.earlier}>
          <Button variant="ghost" small onClick={earlier}>
            Earlier
          </Button>
        </div>
      )}
    </div>
  );
}
