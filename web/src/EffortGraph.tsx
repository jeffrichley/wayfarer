import { useEffect, useState } from "react";

import type { TicketGraph } from "./api";
import { Pane } from "./Frame";
import { GraphCanvas, type Selection } from "./GraphCanvas";
import { command, connect, useItems } from "./store";

// An effort's ticket graph: for now the canvas alone. The screen around it, the
// tally, the panel and arming the cascade, is #55's.
export function EffortGraph({ effort }: { effort: number }) {
  useEffect(connect, []);
  // A screen that shows an effort asks for it to be read (ADR-0003).
  useEffect(() => {
    void command(`/api/efforts/${effort}/read`);
  }, [effort]);
  const graph = useItems((items) => items[`graph:${effort}`] as TicketGraph | undefined);
  const [selected, setSelected] = useState<Selection>(null);
  return (
    <Pane>{graph !== undefined && <GraphCanvas graph={graph} selected={selected} onSelect={setSelected} />}</Pane>
  );
}
