import { useEffect, useState } from "react";

// The clock a screen reads, to the minute: home's dateline, and how long a
// ticket on the graph has been building.
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const tick = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(tick);
  }, []);
  return now;
}

// A time on the reader's own clock, as the prototype stamps it: 09:05.
export function clock(at: string): string {
  const time = new Date(at);
  return [time.getHours(), time.getMinutes()].map((n) => String(n).padStart(2, "0")).join(":");
}
