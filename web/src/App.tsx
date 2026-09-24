import { type ReactNode, useEffect } from "react";

import { Desk } from "./Desk";
import { EffortGraph } from "./EffortGraph";
import { Gallery } from "./gallery/Gallery";
import { connect } from "./store";
import { TheLine } from "./TheLine";

export function App() {
  // The server answers every path that is not the API with this page, and the
  // page routes itself (ADR-0004).
  if (window.location.pathname === "/gallery") {
    return <Gallery />;
  }
  const effort = /^\/efforts\/(\d+)$/.exec(window.location.pathname);
  if (effort !== null) {
    return <EffortGraph effort={Number(effort[1])} />;
  }
  if (window.location.pathname === "/desk") {
    return <Screen screen={<Desk />} />;
  }
  return <Screen screen={<TheLine />} />;
}

// A screen fed by the page's one stream.
function Screen({ screen }: { screen: ReactNode }) {
  useEffect(connect, []);
  return screen;
}
