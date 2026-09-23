import type { ReactNode } from "react";

// The small typographic pieces that carry meaning (docs/design/visual-language.md).

// The small uppercase mono label above a heading or a block.
export function Kicker({ children }: { children: ReactNode }) {
  return <span className="kicker">{children}</span>;
}

// The quiet line beneath a heading.
export function Meta({ children }: { children: ReactNode }) {
  return <p className="meta">{children}</p>;
}

export function Chip({ children }: { children: ReactNode }) {
  return <span className="chip">{children}</span>;
}

export function Rule() {
  return <hr className="rule" />;
}

// A thing is called by its name, and its id rides small and in mono after it
// (principle 3). A card, a desk row, a chronicle line and a screen head all draw
// the pair with this, so it looks the same in all of them. A link's text is the
// name, never the id.
export function Named({ name, n, href }: { name: string; n: number; href?: string }) {
  return (
    <>
      {href === undefined ? (
        name
      ) : (
        <a className="nm" href={href}>
          {name}
        </a>
      )}
      <span className="id">{`#${n}`}</span>
    </>
  );
}
