import { useEffect, useRef, useState } from "react";

import type { Cascade } from "./api";
import { Button } from "./Button";
import { command } from "./store";
import styles from "./Arming.module.css";

// Arming the effort's cascade: the ticket graph's one primary action, and the
// only way a session ever starts (#14). It confirms in one line, in place of
// the button, naming how many tickets are takeable and the cap, since that is
// what arming is about to spend. Once armed it says how the cascade stands; a
// paused one is resumed from here, which is arming it again.
export function Arming({ cascade }: { cascade: Cascade }) {
  const [asking, setAsking] = useState(false);
  // Sent holds until the stream says the cascade moved, so the button does not
  // come back in the moment between the command's answer and its effect.
  const [sentAt, setSentAt] = useState<string | null>(null);
  const at = `${cascade.armed}:${cascade.paused}`;
  const sent = sentAt === at;
  const here = useRef<HTMLDivElement>(null);
  const moved = useRef(false);

  // Focus follows the line it swaps in: onto Arm when it asks, back to the
  // button when the person backs out, as a menu returns it to its button.
  useEffect(() => {
    if (moved.current) {
      here.current?.querySelector<HTMLElement>(".btn")?.focus();
    }
  }, [asking]);

  const ask = (next: boolean) => {
    moved.current = true;
    setAsking(next);
  };

  const send = (path: string) => {
    setSentAt(at);
    setAsking(false);
    void command(`/api/efforts/${cascade.effort}/${path}`).then(
      (response) => response.ok || setSentAt(null),
      () => setSentAt(null),
    );
  };

  let body;
  if (cascade.armed && !cascade.paused) {
    body = <p className={styles.line}>{standing(cascade)}</p>;
  } else if (cascade.armed) {
    body = (
      <>
        <p className={styles.line}>{`Armed · paused${cascade.reason ? `: ${cascade.reason}` : ""}`}</p>
        <Button variant="primary" disabled={sent} onClick={() => send("resume")} piece="resume-cascade">
          Resume the cascade
        </Button>
      </>
    );
  } else if (asking) {
    body = (
      <p className={styles.line} data-piece="arm-confirm">
        <span>{`${cascade.offer}.`}</span>
        <Button variant="primary" small onClick={() => send("arm")} piece="arm-cascade">
          Arm
        </Button>
        <Button variant="ghost" small onClick={() => ask(false)}>
          Not yet
        </Button>
      </p>
    );
  } else {
    body = (
      <Button variant="primary" disabled={sent} onClick={() => ask(true)}>
        Arm the cascade
      </Button>
    );
  }
  return (
    <div ref={here} className={styles.arming} data-piece="cascade">
      {body}
    </div>
  );
}

function standing(cascade: Cascade): string {
  if (cascade.waiting) {
    return "Armed · waiting on you: nothing it may start";
  }
  return `Armed · ${cascade.running} running, up to ${cascade.cap} at a time`;
}
