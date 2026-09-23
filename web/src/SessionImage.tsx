import { useEffect, useState } from "react";

import type { BuildEvent, BuildFinished, ImageStatus } from "./api";

// The image this repo's sessions run in (ADR-0005). It is built only when the
// person clicks Build, and its output streams in as Docker prints it.
export function SessionImage() {
  const [status, setStatus] = useState<ImageStatus | null>(null);
  const [output, setOutput] = useState<string[]>([]);
  const [finished, setFinished] = useState<BuildFinished | null>(null);

  // Bumped to read the status again, after a click and when a build finishes.
  const [asked, setAsked] = useState(0);
  const refresh = () => setAsked((n) => n + 1);

  useEffect(() => {
    let current = true;
    void fetch("/api/image")
      .then((response) => response.json() as Promise<ImageStatus>)
      .then((read) => {
        if (current) setStatus(read);
      });
    return () => {
      current = false;
    };
  }, [asked]);

  const build = async () => {
    setOutput([]);
    setFinished(null);
    const response = await fetch("/api/image/build", { method: "POST" });
    refresh();
    if (response.status !== 202) {
      return;
    }
    const stream = new EventSource("/api/image/build");
    stream.onmessage = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as BuildEvent;
      if (event.kind === "output") {
        setOutput((lines) => [...lines, event.line]);
      } else {
        stream.close();
        setFinished(event);
        refresh();
      }
    };
  };

  if (status === null) {
    return null;
  }

  return (
    <section data-piece="session-image" aria-labelledby="session-image-title">
      <h2 id="session-image-title">Session image</h2>
      {status.refusal !== null ? (
        <p role="alert">{status.refusal}</p>
      ) : (
        <>
          <p>
            <code>{status.tag}</code>{" "}
            {status.ready ? "is built and passed its probe." : "has not been built."}
          </p>
          <button type="button" onClick={() => void build()} disabled={status.building}>
            {status.building ? "Building…" : "Build"}
          </button>
        </>
      )}
      {finished !== null && (
        <>
          {finished.error !== null && <p role="alert">{finished.error}</p>}
          <ul>
            {finished.checks.map((check) => (
              <li key={check.name}>
                {check.passed ? "✓" : "✗"} {check.name}: {check.detail}
              </li>
            ))}
          </ul>
        </>
      )}
      {output.length > 0 && <pre>{output.join("\n")}</pre>}
    </section>
  );
}
