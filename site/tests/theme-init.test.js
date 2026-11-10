import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";

const code = readFileSync(new URL("../src/theme-init.js", import.meta.url), "utf8");
const run = (localStorage) => {
  const dataset = {};
  vm.runInNewContext(code, { document: { documentElement: { dataset } }, localStorage });
  return dataset;
};

test("stored dark sets data-theme", () => {
  assert.equal(run({ getItem: () => "dark" }).theme, "dark");
});
test("stored garbage leaves it unset", () => {
  assert.equal(run({ getItem: () => "evil" }).theme, undefined);
});
test("a throwing localStorage does not throw", () => {
  const ctx = { document: { documentElement: { dataset: {} } } };
  Object.defineProperty(ctx, "localStorage", { get() { throw new Error("blocked"); } });
  vm.runInNewContext(code, ctx);
  assert.equal(ctx.document.documentElement.dataset.theme, undefined);
});
