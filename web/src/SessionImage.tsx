import { useEffect } from "react";
import { useShallow } from "zustand/react/shallow";

import type { BuildFinished, BuildOutput, ImageStatus } from "./api";
import { command, useItems } from "./store";

// The image this repo's sessions run in (ADR-0005). It is built only when the
// person clicks Build, and its output streams in as Docker prints it.
export function SessionImage() {
  const status = useItems((items) => items["image"] as ImageStatus | undefined);
  const finished = useItems((items) => items["build_finished"] as BuildFinished | undefined);
  const output = useItems(
    useShallow((items) =>
      Object.values(items)
        .filter((item): item is BuildOutput => item.kind === "build_output")
        .sort((a, b) => a.number - b.number)
        .map((item) => item.line),
    ),
  );

  // The layer may have changed on disk since anything last looked.
  useEffect(() => {
    void command("/api/image/read");
  }, []);

  if (status === undefined) {
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
          <button
            type="button"
            onClick={() => void command("/api/image/build")}
            disabled={status.building}
          >
            {status.building ? "Building…" : "Build"}
          </button>
        </>
      )}
      {finished !== undefined && (
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
