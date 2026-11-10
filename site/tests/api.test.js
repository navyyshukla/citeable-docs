import test from "node:test";
import assert from "node:assert/strict";
import { createApi, describeError } from "../src/api.js";

const BASE = "https://api.example";
const TOKEN = "Ab3_-".repeat(8) + "xyz";

function reply(status, body) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}
function recorder(response) {
  const calls = [];
  const fetchFn = async (url, init) => { calls.push({ url, init }); return response; };
  return { calls, fetchFn };
}

test("ask sends POST /ask with bearer token and a JSON question", async () => {
  const { calls, fetchFn } = recorder(reply(200, { status: "answered", text: "hi" }));
  const out = await createApi({ baseUrl: BASE, fetchFn }).ask(TOKEN, "how?");
  assert.deepEqual(out, { status: "answered", text: "hi" });
  assert.equal(calls[0].url, `${BASE}/ask`);
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers.Authorization, `Bearer ${TOKEN}`);
  assert.equal(calls[0].init.headers["Content-Type"], "application/json");
  assert.deepEqual(JSON.parse(calls[0].init.body), { question: "how?" });
});

test("a trailing slash on the base url is tolerated", async () => {
  const { calls, fetchFn } = recorder(reply(200, {}));
  await createApi({ baseUrl: BASE + "/", fetchFn }).ask(TOKEN, "q");
  assert.equal(calls[0].url, `${BASE}/ask`);
});

test("feedback sends request_id, rating and comment", async () => {
  const { calls, fetchFn } = recorder(reply(200, { ok: true }));
  await createApi({ baseUrl: BASE, fetchFn }).feedback(TOKEN, "rid-1", -1, "wrong key");
  assert.equal(calls[0].url, `${BASE}/feedback`);
  assert.deepEqual(JSON.parse(calls[0].init.body), { request_id: "rid-1", rating: -1, comment: "wrong key" });
  await createApi({ baseUrl: BASE, fetchFn }).feedback(TOKEN, "rid-2", 1);
  assert.deepEqual(JSON.parse(calls[1].init.body), { request_id: "rid-2", rating: 1, comment: null });
});

test("ask throws an error carrying status and the friendly message", async () => {
  const { fetchFn } = recorder(reply(401, { error: "bad token" }));
  await assert.rejects(createApi({ baseUrl: BASE, fetchFn }).ask(TOKEN, "q"), (e) => {
    assert.equal(e.status, 401);
    assert.match(e.message, /invite link isn't valid/);
    return true;
  });
});

test("a network failure becomes a friendly error with status null", async () => {
  const fetchFn = async () => { throw new TypeError("failed to fetch"); };
  await assert.rejects(createApi({ baseUrl: BASE, fetchFn }).ask(TOKEN, "q"), (e) => {
    assert.equal(e.status, null);
    assert.match(e.message, /Couldn't reach the server/);
    return true;
  });
});

test("an unreadable body on a failure still gives a friendly error", async () => {
  const fetchFn = async () => ({ ok: false, status: 503, json: async () => { throw new Error("html"); } });
  await assert.rejects(createApi({ baseUrl: BASE, fetchFn }).ask(TOKEN, "q"), (e) => {
    assert.equal(e.status, 503);
    assert.match(e.message, /busy/);
    return true;
  });
});

test("a 200 with a body that is not JSON is an error, not a crash", async () => {
  const fetchFn = async () => ({ ok: true, status: 200, json: async () => { throw new Error("x"); } });
  await assert.rejects(createApi({ baseUrl: BASE, fetchFn }).ask(TOKEN, "q"), (e) => {
    assert.ok(e instanceof Error && e.message.length > 0);
    return true;
  });
});

test("describeError texts", () => {
  assert.equal(
    describeError(401, null),
    "This invite link isn't valid or was withdrawn. Ask the person who sent it for a new one.",
  );
  const limit = "You have used your questions for today. Try again after 00:00 UTC.";
  assert.equal(describeError(429, { error: limit }), limit);
  assert.match(describeError(429, null), /limit/i);
  assert.equal(describeError(503, { error: "x" }), "The assistant is busy. Try again in a minute.");
  assert.equal(
    describeError(null, null),
    "Couldn't reach the server. Check your connection and try again.",
  );
  assert.equal(describeError(400, { error: "Question is too long." }), "Question is too long.");
  assert.match(describeError(500, null), /went wrong/i);
});

test("describeError never returns non-text bodies", () => {
  assert.match(describeError(429, { error: { nested: 1 } }), /limit/i);
  assert.match(describeError(400, { error: 42 }), /went wrong|check/i);
});

test("health is true on 200, false on a bad status, false when fetch rejects, never throws", async () => {
  assert.equal(await createApi({ baseUrl: BASE, fetchFn: async () => reply(200, {}) }).health(), true);
  assert.equal(await createApi({ baseUrl: BASE, fetchFn: async () => reply(503, {}) }).health(), false);
  const boom = async () => { throw new Error("offline"); };
  assert.equal(await createApi({ baseUrl: BASE, fetchFn: boom }).health(), false);
});

test("a fetch that never resolves is cut off at timeoutMs", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const hang = () => new Promise(() => {}); // ignores the abort signal on purpose
  const api = createApi({ baseUrl: BASE, fetchFn: hang, timeoutMs: 45000 });
  const pending = api.ask(TOKEN, "q");
  t.mock.timers.tick(44999);
  let settled = false;
  pending.catch(() => {}).finally(() => { settled = true; });
  await Promise.resolve();
  assert.equal(settled, false);
  t.mock.timers.tick(1);
  await assert.rejects(pending, (e) => {
    assert.equal(e.status, null);
    assert.match(e.message, /Couldn't reach the server/);
    return true;
  });
});

test("the default timeout is above the 22.9 s cold start", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const hang = () => new Promise(() => {});
  const pending = createApi({ baseUrl: BASE, fetchFn: hang }).ask(TOKEN, "q");
  t.mock.timers.tick(30000);
  let settled = false;
  pending.catch(() => {}).finally(() => { settled = true; });
  await Promise.resolve();
  assert.equal(settled, false); // still waiting at 30 s
  t.mock.timers.tick(15000);
  await assert.rejects(pending);
});
