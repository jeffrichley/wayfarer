import type { ReactNode } from "react";

import styles from "./Gallery.module.css";

// What a widget's gallery file builds its sections from: the section, the bare
// box each specimen sits in, and the gallery's shared layout.
export { styles as layout };

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h2>{title}</h2>
      {children}
    </section>
  );
}

export function Specimen({ name, children }: { name: string; children: ReactNode }) {
  return (
    <div className={styles.specimen} data-specimen={name}>
      {children}
    </div>
  );
}
