import test from "node:test";
import assert from "node:assert/strict";
import { THEME_KEY, parseTheme, effectiveTheme, nextTheme, readTheme, saveTheme, toggleTheme, appliedTheme } from "../src/theme.js";

test("parseTheme accepts only the exact strings", () => {
  assert.equal(parseTheme("light"), "light");
  assert.equal(parseTheme("dark"), "dark");
  for (const bad of ["Dark", "", "evil", null, undefined, 5]) assert.equal(parseTheme(bad), null);
});

test("effectiveTheme: stored wins, else system, garbage ignored", () => {
  assert.equal(effectiveTheme("dark", false), "dark");
  assert.equal(effectiveTheme(null, true), "dark");
  assert.equal(effectiveTheme("garbage", false), "light");
  assert.equal(effectiveTheme("light", true), "light");
});

test("nextTheme is the opposite of the effective theme", () => {
  assert.equal(nextTheme(null, true), "light");
  assert.equal(nextTheme("light", true), "dark");
  assert.equal(nextTheme("dark", false), "light");
});

test("readTheme survives missing or throwing storage", () => {
  assert.equal(readTheme(null), null);
  assert.equal(readTheme({ getItem() { throw new Error("blocked"); } }), null);
  assert.equal(readTheme({ getItem: () => "dark" }), "dark");
  assert.equal(readTheme({ getItem: () => "evil" }), null);
});

test("saveTheme reports failure instead of throwing", () => {
  assert.equal(saveTheme(null, "dark"), false);
  assert.equal(saveTheme({ setItem() { throw new Error("full"); } }, "dark"), false);
  const seen = {};
  assert.equal(saveTheme({ setItem: (k, v) => { seen[k] = v; } }, "dark"), true);
  assert.equal(THEME_KEY, "theme");
  assert.deepEqual(seen, { theme: "dark" });
});

const root = (theme) => ({ dataset: theme ? { theme } : {} });

test("toggleTheme keeps flipping when storage is blocked (the page, not storage, is the truth)", () => {
  for (const storage of [null, { setItem() { throw new Error("blocked"); } }]) {
    const r = root(null); // no saved choice, light device
    assert.equal(appliedTheme(r, false), "light");
    assert.equal(toggleTheme(r, storage, false), "dark");
    assert.equal(r.dataset.theme, "dark");
    assert.equal(appliedTheme(r, false), "dark");
    assert.equal(toggleTheme(r, storage, false), "light");
    assert.equal(r.dataset.theme, "light");
  }
});

test("toggleTheme saves the choice when storage works, and appliedTheme ignores garbage", () => {
  const seen = {};
  const r = root("dark");
  assert.equal(toggleTheme(r, { setItem: (k, v) => { seen[k] = v; } }, true), "light");
  assert.deepEqual(seen, { theme: "light" });
  assert.equal(appliedTheme(root("evil"), true), "dark"); // falls back to the device setting
});
