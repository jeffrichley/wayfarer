import { type ReactNode, useId, useState } from "react";

import styles from "./Diff.module.css";

// What a reviewer said about a line: who said it, and what.
export type Finding = { by: string; body: ReactNode };

// One line of a file's change. A line with only a new number was added, one with
// only an old number was removed, and one with both is context around them.
export type Line = ({ old: number; new: number } | { old: null; new: number } | { old: number; new: null }) & {
  code: string;
  finding?: Finding;
};

export type FileDiff = { path: string; lines: Line[] };

type Kind = "add" | "del" | "ctx";

function kind(line: Line): Kind {
  return line.old === null ? "add" : line.new === null ? "del" : "ctx";
}

// The sign by shape, and the word it stands for to a person who cannot see it.
const SIGNS: Record<Kind, [string, string | undefined]> = {
  add: ["+", "Added"],
  del: ["−", "Removed"],
  ctx: ["", undefined],
};

function count(file: FileDiff, of: Kind): number {
  return file.lines.filter((line) => kind(line) === of).length;
}

// A file's tab is named for its last two path segments, as the prototype names
// it; the whole path rides in its title.
function label(path: string): string {
  return path.split("/").slice(-2).join("/");
}

// A change as the review desk reads it: a tab per file with its counts, and the
// chosen file's lines with their old and new numbers and a sign. A finding
// about a line sits beneath it. The diff opens on the first file a finding is
// about, since that is where the reviewer is sent (docs/screens/review-desk.md).
// A change touches at least one file.
export function Diff({ files }: { files: [FileDiff, ...FileDiff[]] }) {
  const id = useId();
  const [chosen, choose] = useState(() =>
    Math.max(
      0,
      files.findIndex((file) => file.lines.some((line) => line.finding)),
    ),
  );
  // A list that shrinks under the choice falls back to its first file, so one
  // tab is always the selected one.
  const open = chosen < files.length ? chosen : 0;
  const file = files[open] ?? files[0];

  return (
    <>
      <div className={styles.tabs} role="tablist" aria-label="Changed files">
        {files.map((each, i) => {
          const removed = count(each, "del");
          return (
            <button
              key={each.path}
              type="button"
              role="tab"
              id={`${id}-${i}`}
              aria-controls={`${id}-panel`}
              aria-selected={i === open}
              className={styles.tab}
              title={each.path}
              onClick={() => choose(i)}
            >
              {label(each.path)}
              <span className={styles.d}>
                {`+${count(each, "add")}${removed ? ` −${removed}` : ""}`}
              </span>
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${id}-panel`} aria-labelledby={`${id}-${open}`}>
        <table className={styles.diff}>
          <tbody>
            {file.lines.flatMap((line, i) => {
              const change = kind(line);
              const [sign, word] = SIGNS[change];
              const row = (
                // Keyed by place: a file's lines run in order, and two may read alike.
                <tr key={i} className={styles[change]}>
                  <td className={styles.ln}>{line.old ?? ""}</td>
                  <td className={styles.ln}>{line.new ?? ""}</td>
                  <td className={styles.sg} aria-label={word}>
                    {sign}
                  </td>
                  {/* An empty line keeps its height. */}
                  <td className={styles.code}>{line.code || " "}</td>
                </tr>
              );
              return line.finding
                ? [
                    row,
                    <tr key={`${i}-finding`} className={styles.note}>
                      <td colSpan={4}>
                        <span className={styles.by}>{line.finding.by}</span>
                        <p>{line.finding.body}</p>
                      </td>
                    </tr>,
                  ]
                : [row];
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
