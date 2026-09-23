import { Route, type RouteProps } from "./Route";
import { layout, Section, Specimen } from "./gallery/Section";

// Where an effort is on the line: mid-build with two landed, sliced and waiting
// to be built, and still charting the way.
const ROUTES: [string, RouteProps][] = [
  [
    "route-building",
    {
      reached: "landed",
      current: "build",
      stations: {
        wayfinder: { glyph: "done", out: "7 decisions", href: "#map" },
        spec: { glyph: "done", out: "16 stories · 2 without a ticket", href: "#spec" },
        tickets: { glyph: "done", out: "9 tickets · 1 takeable", href: "#tickets" },
        build: { glyph: "ask", out: "2 building · 1 asking", href: "#build" },
        review: { glyph: "review", out: "1 PR waiting on you", href: "#desk" },
        landed: {
          glyph: "flag",
          out: "2 of 9",
          dots: [true, true, false, false, false, false, false, false, false],
        },
      },
    },
  ],
  [
    "route-sliced",
    {
      reached: "tickets",
      current: "tickets",
      stations: {
        wayfinder: { glyph: "done", out: "6 decisions · way clear", href: "#map" },
        spec: { glyph: "done", out: "Spec #168 · 12 stories", href: "#spec" },
        tickets: { glyph: "take", out: "5 tickets · 2 takeable", href: "#tickets" },
        build: { glyph: "pending", out: "—", why: "Opens once a ticket is taken" },
        review: { glyph: "pending", out: "—", why: "Opens once a ticket has a PR" },
        landed: { glyph: "pending", out: "—" },
      },
    },
  ],
  [
    "route-charting",
    {
      reached: "wayfinder",
      current: "wayfinder",
      stations: {
        wayfinder: { glyph: "building", out: "3 decided · 3 patches of fog", href: "#map" },
        spec: { glyph: "pending", out: "After the way is clear", why: "Opens once the map's way is clear" },
        tickets: { glyph: "pending", out: "—", why: "Opens once the map's way is clear" },
        build: { glyph: "pending", out: "—", why: "Opens once the map's way is clear" },
        review: { glyph: "pending", out: "—", why: "Opens once the map's way is clear" },
        landed: { glyph: "pending", out: "—" },
      },
    },
  ],
];

export default function RouteGallery() {
  return (
    <Section title="Route band">
      <div className={layout.stack}>
        {ROUTES.map(([name, route]) => (
          <Specimen key={name} name={name}>
            <div className={layout.bar}>
              <Route {...route} />
            </div>
          </Specimen>
        ))}
      </div>
    </Section>
  );
}
