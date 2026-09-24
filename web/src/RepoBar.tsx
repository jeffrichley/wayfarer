import type { Home, NeedsYou } from "./api";
import { atWorkHref, deskHref } from "./links";
import { useItems } from "./store";
import { TopBar } from "./TopBar";

// The top bar on a screen that spans the repo rather than one effort: home, At
// work and the desk. The ticket graph carries it too, until an effort's screens
// have the effort switcher. Home's item says the repo, how many efforts move and
// what is running, and Needs you says what waits on the person.
export function RepoBar() {
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
