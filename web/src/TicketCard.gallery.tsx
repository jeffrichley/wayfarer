import { type Doing, TicketCard } from "./TicketCard";
import { layout, Section, Specimen } from "./gallery/Section";

// A ticket in every state it shows a card in, with what its foot needs. The two
// blocked forms and waiting on a slot are states of their own here, since each
// foot says something different (#48).
type Card = { name: string; number: number } & Doing;
const TAKEABLE: Card = { name: "Show compliance status on My Books", number: 132, state: "takeable", atCap: false };
const CARDS: [string, Card][] = [
  ["landing", { name: "Flag peaks above −3 dB", number: 127, state: "landing" }],
  ["building", { name: "Flag a noise floor above −60 dB", number: 128, state: "building", minutes: 12 }],
  ["asked", { name: "Check room tone", number: 130, state: "asked" }],
  ["held", { name: "Warn when no retail sample is chosen", number: 129, state: "held" }],
  ["takeable", TAKEABLE],
  ["takeable-at-cap", { ...TAKEABLE, atCap: true }],
  [
    "blocked-on-one",
    { name: "Explain a failing chapter", number: 131, state: "blocked", waitingOn: ["Check room tone"] },
  ],
  [
    "blocked-on-many",
    { name: "Block ACX export", number: 133, state: "blocked", waitingOn: ["a", "b", "c", "d", "e"] },
  ],
  [
    "long-name",
    {
      name: "Explain a loudness failure in plain words, with the chapter, the value it measured, the limit it broke and the moment it happens",
      number: 134,
      state: "blocked",
      waitingOn: ["Normalise loudness to the ACX range on request"],
    },
  ],
];
const CARD_SIZES = ["full", "name-only"] as const;

export default function TicketCardGallery() {
  return (
    <Section title="Ticket cards">
      {CARD_SIZES.map((size) => (
        <div key={size} className={layout.row}>
          {CARDS.map(([state, card]) => (
            <Specimen key={state} name={`${size}-${state}`}>
              <TicketCard size={size} {...card} />
            </Specimen>
          ))}
          <Specimen name={`${size}-selected`}>
            <TicketCard size={size} {...TAKEABLE} selected />
          </Specimen>
        </div>
      ))}
    </Section>
  );
}
