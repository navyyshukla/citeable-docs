import test from "node:test";
import assert from "node:assert/strict";
import { escapeHtml, renderAnswerHtml } from "../src/render.js";

const JOIN = { n: 1, title: "Join › How", url: "https://www.visidata.org/docs/join/" };
const A_JOIN =
  '<a href="https://www.visidata.org/docs/join/" target="_blank" rel="noopener noreferrer">';

test("script tags are escaped, never emitted", () => {
  const out = renderAnswerHtml("<script>alert(1)</script>", []);
  assert.ok(!out.includes("<script"));
  assert.ok(out.includes("&lt;script&gt;"));
});

test("img with onerror is escaped", () => {
  const out = renderAnswerHtml("<img src=x onerror=alert(1)>", []);
  assert.ok(!out.includes("<img"));
});

test("markdown link with a javascript: target makes no anchor", () => {
  const out = renderAnswerHtml("[click](javascript:alert(1))", []);
  assert.ok(!out.includes("<a"));
  assert.ok(!/href\s*=\s*["']?javascript/i.test(out));
});

test("a known citation becomes exactly one safe link", () => {
  const out = renderAnswerHtml("See [1].", [JOIN]);
  assert.equal(out.split("<a ").length - 1, 1);
  assert.ok(out.includes(A_JOIN + "[1]</a>"));
});

test("an unknown citation number stays plain text", () => {
  const out = renderAnswerHtml("See [99].", [JOIN]);
  assert.ok(!out.includes("<a"));
  assert.ok(out.includes("[99]"));
});

test("two numbers in one bracket link separately", () => {
  const two = { n: 2, title: "Sort", url: "https://www.visidata.org/docs/sort/" };
  const out = renderAnswerHtml("See [1, 2].", [JOIN, two]);
  assert.equal(out.split("<a ").length - 1, 2);
});

for (const url of [
  "javascript:alert(1)",
  "http://www.visidata.org/docs/join/",
  "data:text/html,<b>x</b>",
  'https://x.example/" onmouseover="alert(1)',
  "https://x.example/ y",
  "",
]) {
  test(`citation with an unsafe url is plain text: ${JSON.stringify(url)}`, () => {
    const out = renderAnswerHtml("See [1].", [{ n: 1, title: "t", url }]);
    assert.ok(!out.includes("<a"));
    assert.ok(out.includes("[1]"));
  });
}

test("a quote or ampersand in an allowed url is escaped inside href", () => {
  const out = renderAnswerHtml("See [1].", [
    { n: 1, title: "t", url: "https://www.visidata.org/docs/a?x=1&y=2" },
  ]);
  assert.ok(out.includes('href="https://www.visidata.org/docs/a?x=1&amp;y=2"'));
});

test("bold and inline code, inner tags escaped", () => {
  const out = renderAnswerHtml("**bold** and `code`", []);
  assert.ok(out.includes("<strong>bold</strong>"));
  assert.ok(out.includes("<code>code</code>"));
  const nested = renderAnswerHtml("**<b>x</b>**", []);
  assert.ok(nested.includes("<strong>&lt;b&gt;x&lt;/b&gt;</strong>"));
  assert.ok(!nested.includes("<b>"));
});

test("brackets and html inside code are literal", () => {
  const out = renderAnswerHtml("Use `row[1]` or `<b>`.", [JOIN]);
  assert.ok(out.includes("<code>row[1]</code>"));
  assert.ok(out.includes("<code>&lt;b&gt;</code>"));
  assert.ok(!out.includes("<a"));
});

test("bullet list, numbered list, paragraphs", () => {
  const ul = renderAnswerHtml("- a\n- b", []);
  assert.equal(ul, "<ul><li>a</li><li>b</li></ul>");
  const ol = renderAnswerHtml("1. a\n2. b", []);
  assert.equal(ol, "<ol><li>a</li><li>b</li></ol>");
  const paras = renderAnswerHtml("one\n\ntwo", []);
  assert.equal(paras, "<p>one</p><p>two</p>");
  assert.equal(renderAnswerHtml("line\nbreak", []), "<p>line<br>break</p>");
});

test("a paragraph followed by a list", () => {
  assert.equal(renderAnswerHtml("Steps:\n- a\n- b", []), "<p>Steps:</p><ul><li>a</li><li>b</li></ul>");
});

test("empty and odd inputs give an empty string", () => {
  assert.equal(renderAnswerHtml("", []), "");
  assert.equal(renderAnswerHtml("   \n\n  ", []), "");
  assert.equal(renderAnswerHtml(null, []), "");
  assert.equal(renderAnswerHtml(undefined, undefined), "");
});

test("already-escaped input is escaped again, never decoded", () => {
  const out = renderAnswerHtml("&lt;script&gt;", []);
  assert.ok(out.includes("&amp;lt;script&amp;gt;"));
  assert.ok(!out.includes("<script"));
});

test("placeholder look-alikes in the input cannot forge code spans", () => {
  const out = renderAnswerHtml("\u0000C0\u0000 and `x`", []);
  assert.ok(!out.includes("\u0000"));
  assert.ok(out.includes("<code>x</code>"));
});

test("escapeHtml handles all five characters", () => {
  assert.equal(escapeHtml(`<a href="x">'&'</a>`), "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
});
