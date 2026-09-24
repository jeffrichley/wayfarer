import { useEffect } from "react";

import { AtWork } from "./AtWork";
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
  if (window.location.pathname === "/at-work") {
    return <AtWorkPage />;
  }
  return <Home />;
}

function AtWorkPage() {
  useEffect(connect, []);
  return <AtWork />;
}

function Home() {
  useEffect(connect, []);
  return <TheLine />;
}
