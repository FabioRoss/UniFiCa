import { useSyncExternalStore } from "react";

// Day/night mode. index.html sets <html data-theme> before the first paint;
// this keeps it in sync. A saved choice wins; without one the app follows
// the system setting, and picking the system's own mode clears the choice.
export type Theme = "light" | "dark";

const KEY = "theme";
const listeners = new Set<() => void>();
const system = () => window.matchMedia("(prefers-color-scheme: dark)");

function saved(): Theme | null {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
}

function apply(t: Theme) {
  document.documentElement.dataset.theme = t;
  listeners.forEach((f) => f());
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function setTheme(t: Theme) {
  try {
    if (t === (system().matches ? "dark" : "light")) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, t);
  } catch { /* private mode: still switch for this visit */ }
  apply(t);
}

system().addEventListener("change", (e) => {
  if (!saved()) apply(e.matches ? "dark" : "light");
});
// Another tab changed it
window.addEventListener("storage", (e) => {
  if (e.key === KEY) apply(saved() ?? (system().matches ? "dark" : "light"));
});

function subscribe(f: () => void) {
  listeners.add(f);
  return () => { listeners.delete(f); };
}

export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, currentTheme);
}
