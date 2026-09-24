import type { Home, Need, NeedsYou } from "./api";
import { atWorkHref, deskHref } from "./links";
import { useItems } from "./store";
import { TopBar } from "./TopBar";

const NOTHING: Need[] = [];

// The top bar as every screen of the app carries it: the repo, what is working
// and what needs the person, as the server last said (docs/design/shell.md).
export function ShellBar() {
  const home = useItems((items) => items["home"] as Home | undefined);
  const needs = useItems((items) => (items["needs_you"] as NeedsYou | undefined)?.items ?? NOTHING);
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
      needsYou={{ count: needs.length, href: deskHref() }}
    />
  );
}
