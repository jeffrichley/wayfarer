import type { Home, NeedsYou } from "./api";
import { atWorkHref, deskHref } from "./links";
import { useItems } from "./store";
import { TopBar } from "./TopBar";

// The top bar as every screen of the app draws it: the repo, what is at work, and
// how much needs the person, live, from home's items.
export function AppBar() {
  const home = useItems((items) => items["home"] as Home | undefined);
  const needs = useItems((items) => (items["needs_you"] as NeedsYou | undefined)?.items.length ?? 0);
  const repo = home?.repo ?? "No GitHub repo";
  const moving = home?.moving ?? 0;
  return (
    <TopBar
      repo={repo}
      repos={[
        {
          name: repo,
          meta: `${moving} ${moving === 1 ? "effort" : "efforts"} on the line`,
          href: "/",
          current: true,
        },
      ]}
      working={{ count: home?.working.length ?? 0, href: atWorkHref() }}
      needsYou={{ count: needs, href: deskHref() }}
    />
  );
}
