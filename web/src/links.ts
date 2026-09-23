// Where a thing's name goes when it is a link. Every name the page links goes
// through here, so the routes change in one place when the screens they open
// land: an effort opens its ticket graph, and a ticket opens there, selected
// (docs/screens/ticket-graph.md).

export function effortHref(effort: number): string {
  return `/efforts/${effort}`;
}

export function ticketHref(effort: number, ticket: number): string {
  return `${effortHref(effort)}#${ticket}`;
}

// At work, where running sessions are watched; a ticket opens its session there
// (docs/screens/live-build.md).
export function atWorkHref(ticket?: number): string {
  return ticket === undefined ? "/at-work" : `/at-work#${ticket}`;
}

// The desk, where what needs the person is worked through; an item opens there,
// selected (docs/screens/review-desk.md).
export function deskHref(item?: string): string {
  return item === undefined ? "/desk" : `/desk#${item}`;
}
