import { useEffect } from "react";

import { Gallery } from "./gallery/Gallery";
import { SessionImage } from "./SessionImage";
import { connect } from "./store";

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

  return (
    <main>
      <h1>Wayfarer</h1>
      <SessionImage />
    </main>
  );
}
