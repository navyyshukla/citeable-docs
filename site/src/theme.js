// Light/dark choice. Pure functions plus two guarded storage helpers; no DOM here.
export const THEME_KEY = "theme";

export function parseTheme(value) {
  return value === "light" || value === "dark" ? value : null;
}

export function effectiveTheme(stored, systemDark) {
  return parseTheme(stored) ?? (systemDark ? "dark" : "light");
}

export function nextTheme(stored, systemDark) {
  return effectiveTheme(stored, systemDark) === "dark" ? "light" : "dark";
}

export function readTheme(storage) {
  try {
    return parseTheme(storage ? storage.getItem(THEME_KEY) : null);
  } catch {
    return null;
  }
}

export function saveTheme(storage, theme) {
  try {
    if (!storage) return false;
    storage.setItem(THEME_KEY, theme);
    return true;
  } catch {
    return false;
  }
}
