// The browser's names for the shapes Python defines (src/wayfarer/models.py).
// `api.gen.ts` is generated from the server's OpenAPI schema by `pnpm gen:types`;
// never edit it by hand, and never redeclare a shape here (ADR-0004).
import type { components } from "./api.gen";

type Schemas = components["schemas"];

export type Health = Schemas["Health"];
