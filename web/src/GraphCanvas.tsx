import type { ELK, ElkNode } from "elkjs/lib/elk.bundled.js";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { GraphCard, TicketGraph, Wire } from "./api";
import { useNow } from "./clock";
import { type Doing, TicketCard } from "./TicketCard";
import styles from "./GraphCanvas.module.css";

// The ticket graph's canvas: the start line, a card for every ticket still to
// land, and the wires between them (docs/screens/ticket-graph.md). The server
// says what is drawn, how far each ticket is from now and what it waits on
// (ADR-0004); the canvas measures each card and asks elkjs where it goes, with
// the rules #23 settled, and draws the wires in its own SVG.

// What is selected: a ticket by its number, the start line, or nothing. The
// screen holds it, so its panel can show the same thing.
export type Selection = number | "start" | null;

// The start line's node, which every wire from landed work leaves.
const START = "start";

// A card's width, and the start line's nominal height before it is stretched to
// the full height of the graph (docs/screens/ticket-graph.md).
const CARD_WIDTH = 184;
const START_HEIGHT = 128;

// Below this the canvas scrolls rather than shrink text past legibility (#23).
const SCALE_FLOOR = 0.7;
// The canvas's own padding either side, which the graph is fitted inside.
const GUTTER = 48;

// Columns count steps from now: ELK's longest path from the source puts each
// ticket as early as it can start, where every default puts it as late as it
// can go (#23). Rows are ELK's, to cut crossings.
const OPTIONS = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.layered.layering.strategy": "LONGEST_PATH_SOURCE",
  "elk.edgeRouting": "ORTHOGONAL",
  "elk.layered.mergeEdges": "true",
  "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
  "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
  "elk.spacing.nodeNode": "14",
  "elk.layered.spacing.nodeNodeBetweenLayers": "56",
  "elk.layered.spacing.edgeNodeBetweenLayers": "14",
  "elk.layered.spacing.edgeEdgeBetweenLayers": "6",
  "elk.padding": "[top=12,left=4,bottom=12,right=12]",
};
// The start line spans the graph inside that padding.
const PAD_Y = 12;

// elkjs is most of the page's weight, so only a screen with a graph loads it.
let elk: Promise<ELK> | null = null;

function layouter(): Promise<ELK> {
  elk ??= import("elkjs/lib/elk.bundled.js").then(({ default: Elk }) => new Elk());
  return elk;
}

type Point = [number, number];
type Box = { x: number; y: number; width: number; height: number };
type Size = { id: string; width: number; height: number };

type Layout = {
  // What was laid out, so a card the layout has not seen yet waits hidden.
  key: string;
  width: number;
  height: number;
  nodes: Map<string, Box>;
  wires: Map<string, Point[]>;
};

function nodeId(n: number | null): string {
  return n === null ? START : String(n);
}

function wireId(wire: Wire): string {
  return `${nodeId(wire.blocker)}-${wire.blocked}`;
}

async function place(sizes: Size[], wires: Wire[], key: string): Promise<Layout> {
  const graph: ElkNode = {
    id: "root",
    layoutOptions: OPTIONS,
    children: [{ id: START, width: CARD_WIDTH, height: START_HEIGHT }, ...sizes],
    edges: wires.map((wire) => ({
      id: wireId(wire),
      sources: [nodeId(wire.blocker)],
      targets: [String(wire.blocked)],
    })),
  };
  const laid = await (await layouter()).layout(graph);
  const width = laid.width ?? 0;
  const height = laid.height ?? 0;
  const nodes = new Map<string, Box>(
    (laid.children ?? []).map((c) => [c.id, { x: c.x ?? 0, y: c.y ?? 0, width: c.width ?? 0, height: c.height ?? 0 }]),
  );
  // The start line is a rail the full height of the graph, so a landing moves
  // tickets and never the rail.
  const start = nodes.get(START);
  if (start !== undefined) {
    nodes.set(START, { ...start, y: PAD_Y, height: height - 2 * PAD_Y });
  }
  const railEdge = (start?.x ?? 0) + CARD_WIDTH;
  const routes = new Map<string, Point[]>(
    (laid.edges ?? []).map((edge) => {
      const points: Point[] = (edge.sections ?? []).flatMap((s) => [
        [s.startPoint.x, s.startPoint.y] as Point,
        ...(s.bendPoints ?? []).map((b) => [b.x, b.y] as Point),
        [s.endPoint.x, s.endPoint.y] as Point,
      ]);
      // A wire from the start line leaves it level with the ticket it feeds, so
      // the rail has no trunk: ELK's first run along the rail is dropped.
      if (edge.sources[0] === START && points.length > 0) {
        const from = points.length > 2 ? 2 : points.length - 1;
        const [, y] = points[from] as Point;
        return [edge.id, [[railEdge, y], ...points.slice(from)]];
      }
      return [edge.id, points];
    }),
  );
  return { key, width, height, nodes, wires: routes };
}

// An orthogonal route with its corners rounded.
function path(points: Point[], radius: number): string {
  const [first, ...rest] = points;
  if (first === undefined || rest.length === 0) {
    return "";
  }
  let d = `M${first[0]},${first[1]}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i - 1] as Point;
    const [x, y] = points[i] as Point;
    const [nx, ny] = points[i + 1] as Point;
    const inLength = Math.hypot(x - px, y - py) || 1;
    const outLength = Math.hypot(nx - x, ny - y) || 1;
    const r = Math.min(radius, inLength / 2, outLength / 2);
    d += ` L${x - ((x - px) / inLength) * r},${y - ((y - py) / inLength) * r}`;
    d += ` Q${x},${y} ${x + ((nx - x) / outLength) * r},${y + ((ny - y) / outLength) * r}`;
  }
  const [lx, ly] = points[points.length - 1] as Point;
  return `${d} L${lx},${ly}`;
}

// What a card's foot needs, from what the server says of its ticket.
function doing(card: GraphCard, now: Date): Doing {
  switch (card.state) {
    case "building":
      return {
        state: "building",
        minutes: card.since === null ? 0 : Math.max(0, Math.floor((now.getTime() - Date.parse(card.since)) / 60_000)),
      };
    case "takeable":
      return { state: "takeable", atCap: card.at_cap };
    case "blocked":
      return { state: "blocked", waitingOn: card.waiting_on.map((t) => t.title) };
    case "landed":
    case "closed":
      throw new Error(`#${card.ticket.number} is ${card.state}, which has no card`);
    default:
      return { state: card.state };
  }
}

// The start line: dashed until the first landing, then the course, which every
// landed ticket folds into. Selecting it is how the panel lists them.
function Start({
  landed,
  selected,
  onSelect,
}: {
  landed: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const course = landed > 0;
  const name = course ? `${landed} ${landed === 1 ? "ticket" : "tickets"} landed` : "Nothing landed yet";
  return (
    <button
      type="button"
      className={`${styles.rail} ${course ? styles.course : ""}`}
      aria-pressed={selected}
      aria-label={course ? name : "The start line, nothing landed yet"}
      data-piece="start-line"
      onClick={onSelect}
    >
      <span className={styles.top}>
        <span className={`st ${course ? "st-done" : "st-pending"}`} aria-hidden="true" />
        {course ? "The course so far" : "The start line"}
      </span>
      <span className={styles.name}>{name}</span>
      <span className={styles.foot}>{course ? "Select to list them" : "The course starts here"}</span>
    </button>
  );
}

export function GraphCanvas({
  graph,
  selected,
  onSelect,
}: {
  graph: TicketGraph;
  selected: Selection;
  onSelect: (selection: Selection) => void;
}) {
  const now = useNow();
  const canvas = useRef<HTMLDivElement>(null);
  const measured = useRef(new Map<string, HTMLElement>());
  const asked = useRef<string | null>(null);
  const [layout, setLayout] = useState<Layout | null>(null);
  const [scale, setScale] = useState(1);

  // Each card as it is drawn, so ELK sizes a card with a long name by the height
  // it takes rather than its nominal one (docs/screens/ticket-graph.md). Laid out
  // again only when what it would lay out has changed.
  useLayoutEffect(() => {
    const sizes = graph.cards.map(({ ticket }) => {
      const id = String(ticket.number);
      return { id, width: CARD_WIDTH, height: measured.current.get(id)?.offsetHeight ?? 0 };
    });
    const key = JSON.stringify([sizes, graph.wires]);
    if (key === asked.current) {
      return;
    }
    asked.current = key;
    void place(sizes, graph.wires, key).then((laid) => {
      if (asked.current === key) {
        setLayout(laid);
      }
    });
  });

  // Fitted to the canvas's width, down to the floor and no further.
  const width = layout?.width ?? 0;
  useLayoutEffect(() => {
    const element = canvas.current;
    if (element === null || width === 0) {
      return;
    }
    const fit = new ResizeObserver(() => {
      setScale(Math.max(SCALE_FLOOR, Math.min(1, (element.clientWidth - GUTTER) / width)));
    });
    fit.observe(element);
    return () => fit.disconnect();
  }, [width]);

  // Escape clears the selection wherever focus is, and leaves focus where it is.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onSelect(null);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onSelect]);

  // Selecting a ticket lights what it waits on, back to the start line, and what
  // it frees; the rest dims.
  const chosen = graph.cards.find((card) => card.ticket.number === selected);
  const lit =
    chosen === undefined ? null : new Set([START, ...[chosen.ticket.number, ...chosen.upstream, ...chosen.downstream].map(String)]);
  const hot = (wire: Wire) => chosen !== undefined && (wire.blocker === selected || wire.blocked === selected);
  // The selected ticket's wires are drawn last, over the rest.
  const wires = [...graph.wires].sort((a, b) => Number(hot(a)) - Number(hot(b)));

  const laidOut = layout !== null && graph.cards.every(({ ticket }) => layout.nodes.has(String(ticket.number)));
  const at = (id: string) => {
    const box = layout?.nodes.get(id);
    return box === undefined ? { className: styles.unplaced } : { style: { left: box.x, top: box.y } };
  };
  const remember = (id: string) => (element: HTMLElement | null) => {
    if (element === null) {
      measured.current.delete(id);
    } else {
      measured.current.set(id, element);
    }
  };
  const start = layout?.nodes.get(START);

  return (
    // Clicking empty canvas clears the selection. Escape does the same from the
    // keyboard, anywhere on the page, so this click has its key already.
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div
      ref={canvas}
      className={styles.canvas}
      data-piece="graph-canvas"
      data-laid-out={laidOut}
      onClick={(event) => {
        if (!(event.target as Element).closest("button")) {
          onSelect(null);
        }
      }}
    >
      <div className={styles.wrap} style={{ width: width * scale, height: (layout?.height ?? 0) * scale }}>
        <div
          className={styles.stage}
          data-piece="graph-stage"
          style={{ width, height: layout?.height ?? 0, transform: `scale(${scale})` }}
        >
          <svg width={width} height={layout?.height ?? 0} aria-hidden="true">
            {wires.map((wire) => {
              const id = wireId(wire);
              const both = lit !== null && lit.has(nodeId(wire.blocker)) && lit.has(String(wire.blocked));
              const tone = hot(wire) ? styles.hot : lit !== null && !both ? styles.dim : "";
              return (
                <path
                  key={id}
                  data-wire={id}
                  className={`${styles.wire} ${styles[wire.kind]} ${tone}`}
                  d={path(layout?.wires.get(id) ?? [], 10)}
                />
              );
            })}
          </svg>
          <div
            className={`${styles.node} ${start === undefined ? styles.unplaced : ""}`}
            style={start && { left: start.x, top: start.y, height: start.height }}
          >
            <Start landed={graph.landed.length} selected={selected === "start"} onSelect={() => onSelect("start")} />
          </div>
          {graph.cards.map((card) => {
            const id = String(card.ticket.number);
            const { className, style } = at(id);
            const dim = lit !== null && !lit.has(id) ? styles.dim : "";
            return (
              <div key={id} ref={remember(id)} className={`${styles.node} ${className ?? ""} ${dim}`} style={style}>
                <TicketCard
                  name={card.ticket.title}
                  number={card.ticket.number}
                  size={card.size}
                  selected={selected === card.ticket.number}
                  onSelect={() => onSelect(card.ticket.number)}
                  piece={`ticket-card-${id}`}
                  {...doing(card, now)}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
