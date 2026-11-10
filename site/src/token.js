// Invite token handling. The token arrives after '#' (browsers never send the fragment to a
// server), is kept in localStorage when allowed, and is checked for its shape before use.
// Every storage call is wrapped: private windows and blocked storage must not crash the page.

const KEY = "citeable_token";
const SHAPE = /^[A-Za-z0-9_-]{43}$/; // what the server's looks_like_token accepts

export function readTokenFromHash(hash) {
  if (typeof hash !== "string") return null;
  const m = /^#t=([A-Za-z0-9_-]+)$/.exec(hash);
  return m && SHAPE.test(m[1]) ? m[1] : null;
}

export function loadToken(storage, hash) {
  const fromHash = readTokenFromHash(hash);
  if (fromHash) return { token: fromHash, fromLink: true };
  try {
    const stored = storage.getItem(KEY);
    if (typeof stored === "string" && SHAPE.test(stored)) return { token: stored, fromLink: false };
  } catch {
    // storage blocked or missing: carry on without a saved token
  }
  return { token: null, fromLink: false };
}

export function saveToken(storage, token) {
  if (typeof token !== "string" || !SHAPE.test(token)) return false;
  try {
    storage.setItem(KEY, token);
    return true;
  } catch {
    return false;
  }
}

export function forgetToken(storage) {
  try {
    storage.removeItem(KEY);
  } catch {
    // nothing to forget if storage is blocked
  }
}
