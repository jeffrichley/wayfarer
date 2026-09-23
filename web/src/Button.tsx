import type { ReactNode } from "react";

// Every button the prototype draws: primary, secondary or ghost, at full size or
// small, optionally with a trailing arrow. Disabled is a state, not a look: the
// control stays focusable, says it is unavailable (aria-disabled), and does
// nothing (docs/design/visual-language.md). A button that goes somewhere is a
// link, until it is disabled: then it goes nowhere, and is not drawn as a link.
export type ButtonProps = {
  variant: "primary" | "secondary" | "ghost";
  small?: boolean;
  arrow?: boolean;
  disabled?: boolean;
  children: ReactNode;
} & ({ href: string; onClick?: never } | { href?: never; onClick?: () => void });

export function Button({
  variant,
  small = false,
  arrow = false,
  disabled = false,
  href,
  onClick,
  children,
}: ButtonProps) {
  const className = `btn btn-${variant}${small ? " btn-sm" : ""}${arrow ? " btn-arrow" : ""}`;
  if (href !== undefined && !disabled) {
    return (
      <a className={className} href={href}>
        {children}
      </a>
    );
  }
  return (
    <button
      type="button"
      className={className}
      aria-disabled={disabled || undefined}
      onClick={disabled ? undefined : onClick}
    >
      {children}
    </button>
  );
}
