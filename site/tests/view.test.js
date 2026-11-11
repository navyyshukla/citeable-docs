import test from "node:test";
import assert from "node:assert/strict";
import { resultView, questionState, createBannerState, pageState, startLinks, thinkingText } from "../src/view.js";

const CIT = [
  { n: 1, title: "Join › How to join", url: "https://www.visidata.org/docs/join/#how", docs_version: "3.0" },
  { n: 2, title: "Sort", url: "https://www.visidata.org/docs/sort/" },
];

test("answered: label, body, sources, feedback on", () => {
  const v = resultView({ status: "answered", text: "Use `&` [1].", citations: CIT, closest: [] });
  assert.equal(v.label, "Answered from the docs");
  assert.ok(v.bodyHtml.includes("<code>&amp;</code>"));
  assert.ok(v.bodyHtml.includes('href="https://www.visidata.org/docs/join/#how"'));
  assert.deepEqual(v.sources.map((s) => s.n), [1, 2]);
  assert.equal(v.sources[0].title, "Join › How to join");
  assert.equal(v.showFeedback, true);
});

test("abstained: label, closest pages, no feedback", () => {
  const closest = [{ n: 1, title: "Columns", url: "https://www.visidata.org/docs/columns/" }];
  const v = resultView({ status: "abstained", text: "No answer.", citations: [], closest });
  assert.equal(v.label, "I couldn't find this in the docs");
  assert.deepEqual(v.closest, [{ title: "Columns", url: "https://www.visidata.org/docs/columns/" }]);
  assert.equal(v.showFeedback, false);
  assert.deepEqual(v.sources, []);
});

test("unknown status or junk gives a neutral label and no crash", () => {
  for (const junk of [{ status: "weird", text: "<script>x</script>" }, {}, null, undefined, "text", 5]) {
    const v = resultView(junk);
    assert.equal(v.label, "Something unexpected came back");
    assert.equal(v.showFeedback, false);
    assert.ok(!v.bodyHtml.includes("<script"));
    assert.deepEqual(v.sources, []);
  }
});

test("sources and closest with an unsafe url are dropped", () => {
  const bad = [
    { n: 1, title: "x", url: "javascript:alert(1)" },
    { n: 2, title: "y", url: "http://insecure.example/" },
    { n: 3, title: "z", url: "https://ok.example/" },
  ];
  const a = resultView({ status: "answered", text: "t", citations: bad, closest: bad });
  assert.deepEqual(a.sources.map((s) => s.n), [3]);
  const b = resultView({ status: "abstained", text: "t", citations: bad, closest: bad });
  assert.deepEqual(b.closest.map((s) => s.title), ["z"]);
});

test("missing or wrong-typed lists are treated as empty", () => {
  const v = resultView({ status: "answered", text: "t", citations: "no", closest: null });
  assert.deepEqual(v.sources, []);
  assert.deepEqual(v.closest, []);
});

test("a long unbroken or html-looking title stays text, not markup", () => {
  const v = resultView({ status: "answered", text: "t", citations: [{ n: 1, title: "<b>x</b>", url: "https://ok.example/" }] });
  assert.equal(v.sources[0].title, "<b>x</b>"); // the page sets it with textContent
});

test("questionState: empty, whitespace, exactly 500, 501", () => {
  assert.deepEqual(questionState("", 500), { count: 0, tooLong: false, canAsk: false });
  assert.deepEqual(questionState("   \n ", 500), { count: 0, tooLong: false, canAsk: false });
  assert.deepEqual(questionState("a".repeat(500), 500), { count: 500, tooLong: false, canAsk: true });
  assert.deepEqual(questionState("a".repeat(501), 500), { count: 501, tooLong: true, canAsk: false });
});

test("questionState trims like the server and counts characters, not UTF-16 units", () => {
  assert.equal(questionState("  hi  ", 500).count, 2);
  assert.equal(questionState("😀".repeat(500), 500).canAsk, true); // 500 characters, 1000 units
  assert.equal(questionState("😀".repeat(501), 500).tooLong, true);
});

test("questionState survives non-strings", () => {
  assert.equal(questionState(null, 500).canAsk, false);
  assert.equal(questionState(undefined, 500).count, 0);
});

test("the 'invite not saved' warning survives the health check finishing", () => {
  const b = createBannerState();
  b.show("Your browser would not save the invite link.", "warn");
  b.hide("info"); // what the health check does when the server answers
  assert.equal(b.current().message, "Your browser would not save the invite link.");
  assert.equal(b.current().kind, "warn");
});

test("the health check still hides its own waking banner, and errors are not hidden by it", () => {
  const b = createBannerState();
  b.show("Waking the server up…", "info");
  b.hide("info");
  assert.equal(b.current(), null);
  b.show("Couldn't reach the server.", "error");
  b.hide("info");
  assert.equal(b.current().kind, "error");
  b.hide(); // no kind: hides whatever is showing
  assert.equal(b.current(), null);
});

test("pageState: a forgotten device never shows a stale conversation", () => {
  assert.equal(pageState({ hasToken: false, started: false }), "invite");
  assert.equal(pageState({ hasToken: false, started: true }), "invite");
  assert.equal(pageState({ hasToken: true, started: false }), "welcome");
  assert.equal(pageState({ hasToken: true, started: true }), "chatting");
});

test("startLinks keeps only labelled https links", () => {
  const ok = { text: "What is VisiData? ↗", url: "https://www.visidata.org" };
  const got = startLinks([
    ok,
    { text: "x", url: "javascript:alert(1)" },
    { text: "x", url: "http://plain.example" },
    { text: "", url: "https://a.example" },
    { text: "x", url: 'https://a.example/"onclick=' },
    null, "str", { url: "https://a.example" },
  ]);
  assert.deepEqual(got, [ok]);
  assert.deepEqual(startLinks(undefined), []);
  assert.deepEqual(startLinks("nope"), []);
});

test("thinkingText: plain label first, the wake-up note after 3 seconds", () => {
  assert.equal(thinkingText(0), "Searching the docs…");
  assert.equal(thinkingText(2999), "Searching the docs…");
  assert.match(thinkingText(3000), /server may be waking up/);
  assert.match(thinkingText(3000), /30 seconds/);
});
