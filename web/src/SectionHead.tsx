import type { ReactNode } from "react";

import styles from "./SectionHead.module.css";

// A section of home: its name, a quiet line saying what it holds, and anything
// that belongs on the right, as the line's legend does (prototype/index.html).
export function SectionHead({
  title,
  meta,
  flush = false,
  children,
}: {
  title: string;
  meta: string;
  // Flush with what is above it, as At work sits under Needs you.
  flush?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className={`${styles.head}${flush ? ` ${styles.flush}` : ""}`}>
      <div>
        <h2>{title}</h2>
        <span className="meta">{meta}</span>
      </div>
      {children}
    </div>
  );
}
