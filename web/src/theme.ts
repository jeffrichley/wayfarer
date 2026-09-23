import { useSyncExternalStore } from "react";

// The chart or the night chart. The theme follows the system until the person
// picks one, then remembers it; the page's head script applies the saved choice
// before first paint (docs/design/visual-language.md). The root's `data-theme`
// is the one place it lives, so whoever sets it, every reader agrees.
export type Theme = "light" | "dark";

// The head script in web/index.html reads the same key.
const KEY = "wayfarer.theme";
// How long the root carries `theme-fade`, a little past its .3s transition.
const FADE_MS = 350;

const root = document.documentElement;
const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
let fading: number | undefined;

function current(): Theme {
  return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function saved(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null; // storage blocked
  }
}

function apply(theme: Theme) {
  root.classList.add("theme-fade");
  if (theme === "dark") {
    root.setAttribute("data-theme", "dark");
  } else {
    root.removeAttribute("data-theme");
  }
  window.clearTimeout(fading);
  fading = window.setTimeout(() => root.classList.remove("theme-fade"), FADE_MS);
}

// The person's choice: applied, and remembered over the system's.
export function chooseTheme(theme: Theme) {
  apply(theme);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // storage blocked: the choice lasts this page
  }
}

function subscribe(changed: () => void) {
  const observer = new MutationObserver(changed);
  observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  const followSystem = (event: MediaQueryListEvent) => {
    if (saved() === null) {
      apply(event.matches ? "dark" : "light");
    }
  };
  systemDark.addEventListener("change", followSystem);
  return () => {
    observer.disconnect();
    systemDark.removeEventListener("change", followSystem);
  };
}

// The theme the page is drawn in now.
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, current);
}
