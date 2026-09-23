import { useEffect } from "react";

import { SessionImage } from "./SessionImage";
import { connect } from "./store";

export function App() {
  useEffect(connect, []);

  return (
    <main>
      <h1>Wayfarer</h1>
      <SessionImage />
    </main>
  );
}
