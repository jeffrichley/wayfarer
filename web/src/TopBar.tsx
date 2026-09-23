import {
  type Dispatch,
  type ReactNode,
  type SetStateAction,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";

import { type Glyph } from "./State";
import { chooseTheme, useTheme } from "./theme";
import styles from "./TopBar.module.css";

// The top bar answers: where am I, is anything working, and does anything need
// me? (docs/design/shell.md). Every screen carries it.

// A repo in the repo switcher, with its one-line state.
export type Repo = { name: string; meta: string; href: string; current?: boolean };
// An effort in the effort switcher: its state as a glyph and a sentence, linking
// to wherever the effort is now.
export type Effort = { name: string; meta: string; glyph: Glyph; href: string; current?: boolean };
// An effort that has landed: listed under the rest, and no longer a place to go.
export type Landed = { name: string; meta: string };

export type TopBarProps = {
  repo: string;
  repos: Repo[];
  // Present on an effort's screens, absent on home.
  effort?: { name: string; efforts: Effort[]; landed: Landed[] };
  // Running sessions across the repo, linking to live build.
  working: { count: number; href: string };
  // Everything waiting on the person, linking to the desk.
  needsYou: { count: number; href: string };
};

type Which = "repo" | "effort";

export function TopBar({ repo, repos, effort, working, needsYou }: TopBarProps) {
  // One menu open at a time: opening one is closing the other.
  const [open, setOpen] = useState<Which | null>(null);

  return (
    <header className={`${styles.topbar}${effort ? ` ${styles.hasEffort}` : ""}`} data-piece="topbar">
      <a className={styles.wordmark} href="/">
        <Mark />
        Wayfarer
      </a>
      <span className={styles.sep} aria-hidden="true">
        /
      </span>
      <Switch which="repo" label={repo} open={open} setOpen={setOpen}>
        <RepoItems repos={repos} />
      </Switch>
      {effort && (
        <>
          <span className={styles.sep} aria-hidden="true">
            /
          </span>
          <Switch which="effort" label={effort.name} open={open} setOpen={setOpen}>
            <EffortItems efforts={effort.efforts} landed={effort.landed} />
          </Switch>
        </>
      )}
      <div className={styles.right}>
        <a className={styles.live} href={working.href} data-piece="agents-working">
          {/* Nothing running is nothing spinning. */}
          <span className={`st ${working.count ? "st-building" : "st-pending"}`} aria-hidden="true" />
          <span className={styles.label}>{agents(working.count)}</span>
        </a>
        {/* When nothing waits the badge goes quiet, and stays in place. */}
        <a className={styles.needs} href={needsYou.href} data-piece="needs-you">
          Needs you{" "}
          <span className={`${styles.count}${needsYou.count ? "" : ` ${styles.zero}`}`}>
            {needsYou.count}
          </span>
        </a>
        <ThemeToggle />
      </div>
    </header>
  );
}

function agents(count: number) {
  if (count === 0) {
    return "No agents working";
  }
  return `${count} ${count === 1 ? "agent" : "agents"} working`;
}

// A switcher: a button naming where you are, and a menu of where else to go.
// Escape, or a click anywhere outside it, closes the menu and puts focus back on
// its button, as the prototype's switchers do (docs/design/shell.md). The bar
// holds which one is open, so opening one is closing the other.
function Switch({
  which,
  label,
  open: opened,
  setOpen,
  children,
}: {
  which: Which;
  label: string;
  open: Which | null;
  setOpen: Dispatch<SetStateAction<Which | null>>;
  children: ReactNode;
}) {
  const open = opened === which;
  const id = useId();
  const own = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) {
      return;
    }
    // Only this switcher's own menu: by the time a stale listener runs, the other
    // one may be the menu that is open.
    const onClose = () => setOpen((now) => (now === which ? null : now));
    const lost = () => document.activeElement === null || document.activeElement === document.body;
    const onClick = (event: MouseEvent) => {
      if (own.current?.contains(event.target as Node)) {
        return;
      }
      onClose();
      // A click on nothing focusable drops focus to the page; it goes back to
      // the button. A click on something that took focus keeps it there.
      if (lost()) {
        trigger.current?.focus();
      }
    };
    const onKey = (event: KeyboardEvent) => {
      // Only while focus is in this switcher, or nowhere: the key is not someone
      // else's Escape.
      if (event.key === "Escape" && (lost() || own.current?.contains(document.activeElement))) {
        onClose();
        trigger.current?.focus();
      }
    };
    document.addEventListener("click", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, which, setOpen]);

  return (
    <div className={styles.switch} ref={own}>
      <button
        ref={trigger}
        className={which === "repo" ? styles.repoBtn : styles.effortBtn}
        type="button"
        aria-expanded={open}
        aria-controls={id}
        data-piece={`${which}-switcher`}
        onClick={() => setOpen((now) => (now === which ? null : which))}
      >
        <span>{label}</span>
        <Caret />
      </button>
      {open && (
        <Menu id={id} wide={which === "effort"}>
          {children}
        </Menu>
      )}
    </div>
  );
}

// A switcher's menu, drawn open beneath its button.
export function Menu({
  id,
  wide = false,
  children,
}: {
  id?: string;
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <div id={id} className={`${styles.menu}${wide ? ` ${styles.wide}` : ""}`} data-piece="menu">
      {children}
    </div>
  );
}

// The effort switcher's rows: the efforts on the line, then those that landed.
export function EffortItems({ efforts, landed }: { efforts: Effort[]; landed: Landed[] }) {
  return (
    <>
      {efforts.map((e) => (
        <a key={e.name} href={e.href} aria-current={e.current || undefined}>
          <span className={`st st-${e.glyph}`} aria-hidden="true" />
          <span className={styles.mName}>{e.name}</span>
          <span className={styles.mMeta}>{e.meta}</span>
        </a>
      ))}
      {landed.length > 0 && <div className={styles.menuSep} />}
      {landed.map((e) => (
        <div key={e.name} className={styles.static}>
          <span className="st st-done" aria-hidden="true" />
          <span className={styles.mName}>{e.name}</span>
          <span className={styles.mMeta}>{e.meta}</span>
        </div>
      ))}
    </>
  );
}

// The repo switcher's rows.
export function RepoItems({ repos }: { repos: Repo[] }) {
  return repos.map((r) => (
    <a key={r.name} href={r.href} aria-current={r.current || undefined}>
      <span className={`${styles.mMark} mono`}>{r.name.charAt(0)}</span>
      <span className={styles.mName}>{r.name}</span>
      <span className={styles.mMeta}>{r.meta}</span>
    </a>
  ));
}

// Switches between the chart and the night chart, showing the one it goes to.
function ThemeToggle() {
  const dark = useTheme() === "dark";
  return (
    <button
      type="button"
      className={styles.theme}
      data-piece="theme-toggle"
      aria-label={dark ? "Switch to the light chart" : "Switch to the night chart"}
      title={dark ? "Light chart" : "Night chart"}
      onClick={() => chooseTheme(dark ? "light" : "dark")}
    >
      {dark ? <Sun /> : <Moon />}
    </button>
  );
}

// A small course: a landed point, a line, and the open ring of the next station.
function Mark() {
  return (
    <svg className={styles.mark} viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="3.5" cy="9" r="2.5" fill="currentColor" />
      <path d="M6 9h6" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="14.5" cy="9" r="2.4" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function Caret() {
  return (
    <svg viewBox="0 0 10 10" aria-hidden="true">
      <path d="M2 3.5 5 6.5 8 3.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
    </svg>
  );
}

function Sun() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" aria-hidden="true">
      <circle cx="8" cy="8" r="3" />
      <path d="M8 1.2v1.7M8 13.1v1.7M1.2 8h1.7M13.1 8h1.7M3.2 3.2l1.2 1.2M11.6 11.6l1.2 1.2M3.2 12.8l1.2-1.2M11.6 4.4l1.2-1.2" />
    </svg>
  );
}

function Moon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" aria-hidden="true">
      <path d="M13.4 10.2A5.8 5.8 0 0 1 5.8 2.6a5.8 5.8 0 1 0 7.6 7.6z" />
    </svg>
  );
}
