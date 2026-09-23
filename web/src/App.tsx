import { useEffect } from "react";

import { Gallery } from "./gallery/Gallery";
import { connect } from "./store";
import { TheLine } from "./TheLine";

export function App() {
  // The server answers every path that is not the API with this page, and the
  // page routes itself (ADR-0004).
  if (window.location.pathname === "/gallery") {
    return <Gallery />;
  }
  return <Home />;
}

function Home() {
  useEffect(connect, []);
  return <TheLine />;
}
