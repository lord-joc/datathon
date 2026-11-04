/**
 * Theme: "system" follows prefers-color-scheme; "light" / "dark" are an explicit choice that is
 * remembered in this browser only. The choice is written to html[data-theme]; tokens.css does
 * the rest, so there is no inline script (CSP: script-src 'self').
 */
import { useSyncExternalStore } from "react";

export type ThemeChoice = "system" | "light" | "dark";
export type Theme = "light" | "dark";

const KEY = "prostoriq.theme";
const media = () =>
  typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

let choice: ThemeChoice = "system";
const listeners = new Set<() => void>();

function readStored(): ThemeChoice {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function resolvedTheme(): Theme {
  if (choice !== "system") return choice;
  return media()?.matches ? "dark" : "light";
}

function apply() {
  const root = document.documentElement;
  if (choice === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", choice);
  const theme = resolvedTheme();
  document
    .querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]')
    .forEach((m) => (m.content = theme === "dark" ? "#8F1426" : "#C8102E"));
  listeners.forEach((l) => l());
}

/** Call once before the first render. */
export function initTheme() {
  choice = readStored();
  apply();
  media()?.addEventListener("change", () => {
    if (choice === "system") apply();
  });
}

/** Toggle between light and dark; the first click turns the system value into a choice. */
export function toggleTheme() {
  choice = resolvedTheme() === "dark" ? "light" : "dark";
  try {
    window.localStorage.setItem(KEY, choice);
  } catch {
    // Private mode or blocked storage: the choice still applies to this visit.
  }
  apply();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, resolvedTheme, () => "light");
}
