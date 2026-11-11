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

// The page itself is the truth about which theme is showing (`root` is the <html> element);
// storage only remembers it. So the button keeps working when storage is blocked.
export function appliedTheme(root, systemDark) {
  return effectiveTheme(root.dataset.theme, systemDark);
}

export function toggleTheme(root, storage, systemDark) {
  const next = nextTheme(root.dataset.theme, systemDark);
  root.dataset.theme = next;
  saveTheme(storage, next);
  return next;
}
