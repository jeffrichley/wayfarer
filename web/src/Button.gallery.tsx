import { Button, type ButtonProps } from "./Button";
import { layout, Section, Specimen } from "./gallery/Section";

// Each button variant with the words it carries in the prototype.
const VARIANTS: [ButtonProps["variant"], string][] = [
  ["primary", "Arm the cascade"],
  ["secondary", "Review PR #141"],
  ["ghost", "Queue an agent"],
];
const SIZES = [
  ["", {}],
  ["-small", { small: true }],
  ["-arrow", { arrow: true }],
] as const;

export default function ButtonGallery() {
  return (
    <Section title="Buttons">
      {VARIANTS.map(([variant, label]) => (
        <div key={variant} className={layout.row}>
          {SIZES.flatMap(([size, props]) =>
            [false, true].map((disabled) => (
              <Specimen
                key={`${size}${disabled}`}
                name={`button-${variant}${size}${disabled ? "-disabled" : ""}`}
              >
                <Button variant={variant} {...props} disabled={disabled}>
                  {label}
                </Button>
              </Specimen>
            )),
          )}
        </div>
      ))}
      <div className={layout.row}>
        <Specimen name="button-link">
          <Button variant="secondary" arrow href="#desk">
            Open the desk
          </Button>
        </Specimen>
        <Specimen name="button-link-disabled">
          <Button variant="secondary" arrow href="#desk" disabled>
            Open the desk
          </Button>
        </Specimen>
      </div>
    </Section>
  );
}
