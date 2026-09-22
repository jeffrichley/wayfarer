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
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:7431",
    },
  },
});
