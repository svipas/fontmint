// Light (Catppuccin Latte), dark (Macchiato) or the system's choice, kept in localStorage.
// index.html applies the stored choice before the first paint, so the page never flashes.

export type Theme = "system" | "light" | "dark";

const KEY = "fontmint-theme";

export function storedTheme(): Theme {
  try {
    const theme = localStorage.getItem(KEY);
    return theme === "light" || theme === "dark" ? theme : "system";
  } catch {
    return "system";
  }
}

export const systemDark = () => matchMedia("(prefers-color-scheme: dark)");

export function applyTheme(theme: Theme): void {
  const dark = theme === "dark" || (theme === "system" && systemDark().matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function saveTheme(theme: Theme): void {
  try {
    if (theme === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    // Private windows can refuse storage; the choice then lasts until the page closes.
  }
  applyTheme(theme);
}
