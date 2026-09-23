import type { ReactNode } from "react";

// The page skeleton: the top bar, the route band when the screen has one, and the
// screen below them, filling the viewport. Each region scrolls on its own, never
// the page as a whole, until the 920px breakpoint stacks them into one scroll.
export function Frame({
  bar,
  route,
  children,
}: {
  bar: ReactNode;
  route?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={route === undefined ? "app no-route" : "app"}>
      {bar}
      {route}
      {children}
    </div>
  );
}

// A screen that is one region.
export function Pane({ children }: { children: ReactNode }) {
  return <main className="pane">{children}</main>;
}

// A column beside the screen's page, named for its landmark. Its width is the
// screen's to choose, as each prototype screen sets its own.
export type Side = { label: string; width: number; children: ReactNode };

// A screen with a side column on either hand, or both (live build's lanes and
// evidence rail). The page takes what the sides leave.
export function Split({
  left,
  right,
  children,
}: {
  left?: Side;
  right?: Side;
  children: ReactNode;
}) {
  const columns = [left && `${left.width}px`, "minmax(0, 1fr)", right && `${right.width}px`];
  return (
    <main className="split" style={{ gridTemplateColumns: columns.filter(Boolean).join(" ") }}>
      {left && (
        <aside className="pane side-l" aria-label={left.label}>
          {left.children}
        </aside>
      )}
      <div className="pane">{children}</div>
      {right && (
        <aside className="pane side" aria-label={right.label}>
          {right.children}
        </aside>
      )}
    </main>
  );
}
