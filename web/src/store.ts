import { create } from "zustand";

import type { Item, WireEvent } from "./api";

// Everything the page holds, keyed by id, exactly as the server last said it.
// The page never folds, derives or merges: each event replaces by id (ADR-0004).
type Items = Readonly<Record<string, Item>>;

export const useItems = create<Items>(() => ({}));

function apply(items: Items, event: WireEvent): Items {
  switch (event.kind) {
    case "snapshot":
      return Object.fromEntries(event.items.map((item) => [item.id, item]));
    case "upsert":
      return { ...items, [event.item.id]: event.item };
    case "removal":
      return Object.fromEntries(Object.entries(items).filter(([id]) => id !== event.id));
  }
}

// The page's one stream. EventSource reconnects by itself, carrying the id of
// the last event it saw, and the server resumes from there or sends a snapshot.
export function connect(): () => void {
  const stream = new EventSource("/api/events");
  stream.onmessage = (message: MessageEvent<string>) => {
    const event = JSON.parse(message.data) as WireEvent;
    useItems.setState((items) => apply(items, event), true);
  };
  return () => stream.close();
}

// A command says only that it was accepted; its effect arrives over the stream.
export async function command(path: string): Promise<Response> {
  return fetch(path, { method: "POST" });
}
