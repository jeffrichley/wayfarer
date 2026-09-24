import { useEffect } from "react";

import { command } from "./store";

// A screen that counts from the person's arrival says so to the server as they
// arrive afresh, and never after a reload, which is the same visit: home's
// headline counts from the last visit (#58), and the desk re-ranks its queue
// (#57). A page kept whole in the back-forward cache and shown again is coming
// back, not reloading.

const told = new Set<string>();

function arrive(path: string) {
  const [navigation] = performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
  // Once a document: React may mount the screen twice while developing.
  if (!told.has(path) && navigation?.type !== "reload") {
    void command(path);
  }
  told.add(path);
}

export function useArrival(path: string) {
  useEffect(() => {
    arrive(path);
    const onShow = (event: PageTransitionEvent) => {
      if (event.persisted) {
        void command(path);
      }
    };
    window.addEventListener("pageshow", onShow);
    return () => window.removeEventListener("pageshow", onShow);
  }, [path]);
}
