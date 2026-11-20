/** Light / dark theme: `data-theme` on <html> forces one; without it the OS setting decides. */
export type ThemeMode = "system" | "light" | "dark";
export const THEME_KEY = "tts-stt-theme";
const MODES: ThemeMode[] = ["system", "light", "dark"];

export function loadTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return MODES.includes(v as ThemeMode) ? (v as ThemeMode) : "system";
  } catch {
    return "system"; // storage blocked (private window, previews)
  }
}

export function applyTheme(mode: ThemeMode, root: HTMLElement = document.documentElement): void {
  if (mode === "system") root.removeAttribute("data-theme");
  else root.dataset.theme = mode;
  try {
    localStorage.setItem(THEME_KEY, mode);
  } catch {
    /* only a convenience: the page works without it */
  }
}

export function nextTheme(mode: ThemeMode): ThemeMode {
  return MODES[(MODES.indexOf(mode) + 1) % MODES.length];
}
