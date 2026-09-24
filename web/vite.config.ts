import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The Python process serves the built bundle from inside its package, so the
// wheel carries it and nobody running Wayfarer needs Node (ADR-0004).
// During development the Vite dev server proxies the API to that process.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../src/wayfarer/static",
    emptyOutDir: true,
    // elkjs is one module compiled from Java, 1.4 MB that cannot be split, so it
    // is loaded only by a screen with a graph to lay out (ADR-0004); every other
    // chunk stays well under Vite's 500 kB default.
    chunkSizeWarningLimit: 1500,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:7431",
    },
  },
});
