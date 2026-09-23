import { Gallery } from "./gallery/Gallery";
import { SessionImage } from "./SessionImage";

export function App() {
  // The server answers every path that is not the API with this page, and the
  // page routes itself (ADR-0004).
  if (window.location.pathname === "/gallery") {
    return <Gallery />;
  }
  return (
    <main>
      <h1>Wayfarer</h1>
      <SessionImage />
    </main>
  );
}
