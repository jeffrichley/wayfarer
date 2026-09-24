// The browser's names for the shapes Python defines (src/wayfarer/models/).
// `api.gen.ts` is generated from the server's OpenAPI schema by `pnpm gen:types`;
// never edit it by hand, and never redeclare a shape here (ADR-0004).
import type { components } from "./api.gen";

type Schemas = components["schemas"];

export type Answer = Schemas["Answer"];
export type Asking = Schemas["Asking"];
export type Beat = Schemas["Beat"];
export type BeatKind = Schemas["BeatKind"];
export type Checks = Schemas["Checks"];
export type Desk = Schemas["Desk"];
export type DeskEntry = Schemas["DeskEntry"];
export type Effort = Schemas["Effort"];
export type EffortUnreadable = Schemas["EffortUnreadable"];
export type EnvironmentFailure = Schemas["EnvironmentFailure"];
export type Health = Schemas["Health"];
export type PullRequest = Schemas["PullRequest"];
export type Retry = Schemas["Retry"];
export type Ticket = Schemas["Ticket"];
export type TicketState = Schemas["TicketState"];
export type ImageStatus = Schemas["ImageStatus"];
export type ProbeCheck = Schemas["ProbeCheck"];
export type BuildOutput = Schemas["BuildOutput"];
export type BuildFinished = Schemas["BuildFinished"];
export type ChronicleLine = Schemas["ChronicleLine"];
export type Mention = Schemas["Mention"];
export type Someone = Schemas["Someone"];
export type GraphCard = Schemas["GraphCard"];
export type Home = Schemas["Home"];
export type Lane = Schemas["Lane"];
export type LineRow = Schemas["LineRow"];
export type NeedsYou = Schemas["NeedsYou"];
export type TicketGraph = Schemas["TicketGraph"];
export type Wire = Schemas["Wire"];
export type Need = NeedsYou["items"][number];

// Everything the page's one stream carries, and the items it holds by id.
export type Snapshot = Schemas["Snapshot"];
export type Upsert = Schemas["Upsert"];
export type Removal = Schemas["Removal"];
export type WireEvent = Snapshot | Upsert | Removal;
export type Item = Upsert["item"];
