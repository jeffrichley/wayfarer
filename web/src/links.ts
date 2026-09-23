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
