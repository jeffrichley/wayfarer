// State is a glyph's shape beside its word: never colour, and never a glyph
// alone (docs/design/visual-language.md). The same shape means the same kind
// of state on every screen; the word says what it means for this object.
export type Glyph =
  | "done"
  | "review"
  | "building"
  | "ask"
  | "held"
  | "take"
  | "blocked"
  | "pending"
  | "out";

export function State({
  glyph,
  large = false,
  children,
}: {
  glyph: Glyph;
  large?: boolean;
  children: string;
}) {
  return (
    <span className="state">
      <span className={`st st-${glyph}${large ? " st-lg" : ""}`} aria-hidden="true" />
      {children}
    </span>
  );
}

// A test run: hatched when it went red, solid when it went green.
export function TestRun({ result, children }: { result: "red" | "green"; children: string }) {
  return (
    <span className="state">
      <span className={`tr tr-${result}`} aria-hidden="true" />
      {children}
    </span>
  );
}
