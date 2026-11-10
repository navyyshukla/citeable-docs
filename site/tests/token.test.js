import test from "node:test";
import assert from "node:assert/strict";
import { readTokenFromHash, loadToken, saveToken, forgetToken } from "../src/token.js";

const TOKEN = "Ab3_-".repeat(8) + "xyz"; // 43 characters
const OTHER = "Zy9_-".repeat(8) + "abc";

function memoryStorage(initial = {}) {
  const data = { ...initial };
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; },
  };
}
const brokenStorage = {
  getItem() { throw new Error("blocked"); },
  setItem() { throw new Error("blocked"); },
  removeItem() { throw new Error("blocked"); },
};

test("a valid fragment returns the token", () => {
  assert.equal(readTokenFromHash(`#t=${TOKEN}`), TOKEN);
});

for (const [label, hash] of [
  ["empty", ""],
  ["no value", "#t="],
  ["42 characters", `#t=${TOKEN.slice(0, 42)}`],
  ["44 characters", `#t=${TOKEN}a`],
  ["query string instead of fragment", `?t=${TOKEN}`],
  ["wrong key", `#x=${TOKEN}`],
  ["extra text after", `#t=${TOKEN}&x=1`],
  ["bad character", `#t=${TOKEN.slice(0, 42)}!`],
  ["not a string", null],
  ["undefined", undefined],
]) {
  test(`readTokenFromHash rejects: ${label}`, () => {
    assert.equal(readTokenFromHash(hash), null);
  });
}

test("a link token wins over a stored one and is marked fromLink", () => {
  const s = memoryStorage({ citeable_token: OTHER });
  assert.deepEqual(loadToken(s, `#t=${TOKEN}`), { token: TOKEN, fromLink: true });
});

test("without a link the stored token is used", () => {
  const s = memoryStorage();
  assert.equal(saveToken(s, TOKEN), true);
  assert.deepEqual(loadToken(s, ""), { token: TOKEN, fromLink: false });
});

test("a stored value that is not token-shaped is ignored", () => {
  const s = memoryStorage({ citeable_token: "junk" });
  assert.deepEqual(loadToken(s, ""), { token: null, fromLink: false });
});

test("nothing anywhere gives no token", () => {
  assert.deepEqual(loadToken(memoryStorage(), ""), { token: null, fromLink: false });
});

test("blocked storage never throws", () => {
  assert.deepEqual(loadToken(brokenStorage, ""), { token: null, fromLink: false });
  assert.equal(saveToken(brokenStorage, TOKEN), false);
  assert.doesNotThrow(() => forgetToken(brokenStorage));
});

test("a link still works when storage is blocked", () => {
  assert.deepEqual(loadToken(brokenStorage, `#t=${TOKEN}`), { token: TOKEN, fromLink: true });
});

test("missing storage object (null) is handled", () => {
  assert.deepEqual(loadToken(null, ""), { token: null, fromLink: false });
  assert.equal(saveToken(null, TOKEN), false);
});

test("saveToken refuses a token that is not token-shaped", () => {
  const s = memoryStorage();
  assert.equal(saveToken(s, "junk"), false);
  assert.deepEqual(s.data, {});
});

test("forgetToken removes it", () => {
  const s = memoryStorage();
  saveToken(s, TOKEN);
  forgetToken(s);
  assert.deepEqual(loadToken(s, ""), { token: null, fromLink: false });
});
