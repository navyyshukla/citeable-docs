import test from "node:test";
import assert from "node:assert/strict";
import { enterAction, growHeight, scrollBehavior, isTouchDevice } from "../src/input.js";

const key = (o) => ({ key: "Enter", shiftKey: false, ctrlKey: false, metaKey: false, isComposing: false, ...o });

test("enterAction on a computer", () => {
  assert.equal(enterAction(key({}), false), "send");
  assert.equal(enterAction(key({ shiftKey: true }), false), "default");
  assert.equal(enterAction(key({ key: "a" }), false), "default");
  assert.equal(enterAction(key({ isComposing: true }), false), "default");
});
test("enterAction on touch: plain Enter is a new line, Ctrl/Meta+Enter sends", () => {
  assert.equal(enterAction(key({}), true), "default");
  assert.equal(enterAction(key({ ctrlKey: true }), true), "send");
  assert.equal(enterAction(key({ metaKey: true }), true), "send");
});
test("growHeight clamps", () => {
  assert.equal(growHeight(10, 24, 192), 24);
  assert.equal(growHeight(500, 24, 192), 192);
  assert.equal(growHeight(100, 24, 192), 100);
});
test("scrollBehavior respects reduced motion", () => {
  assert.equal(scrollBehavior(true), "auto");
  assert.equal(scrollBehavior(false), "smooth");
});
test("isTouchDevice", () => {
  assert.equal(isTouchDevice(undefined), false);
  assert.equal(isTouchDevice((q) => ({ matches: q === "(pointer: coarse)" })), true);
  assert.equal(isTouchDevice(() => ({ matches: false })), false);
});
