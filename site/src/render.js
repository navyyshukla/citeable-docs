// Safe renderer for generated answers. The whole text is escaped first; only a few shapes are
// then put back: paragraphs, **bold**, `code`, bullet and numbered lists, and [n] links.
// A [n] becomes a link only when n is in `citations` and its url is a plain https URL.
// Allowed output tags: p, strong, code, ul, ol, li, a, br.

const ESCAPES = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ESCAPES[c]);
}

function safeUrl(url) {
  // https only, and nothing that could break out of an attribute or add a second URL.
  return typeof url === "string" && url.startsWith("https://") && !/[\s"'<>`\\\u0000-\u001f]/.test(url);
}

function inline(escaped, byNumber) {
  const codes = [];
  // Code spans first, so brackets and asterisks inside them stay literal.
  let s = escaped.replace(/`([^`\n]+)`/g, (_, body) => {
    codes.push(`<code>${body}</code>`);
    return `\u0000C${codes.length - 1}\u0000`;
  });
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (whole, nums) =>
    nums
      .split(",")
      .map((raw) => {
        const n = Number(raw.trim());
        const c = byNumber.get(n);
        if (!c || !safeUrl(c.url)) return `[${raw.trim()}]`;
        return `<a href="${escapeHtml(c.url)}" target="_blank" rel="noopener noreferrer">[${n}]</a>`;
      })
      .join(", "),
  );
  return s.replace(/\u0000C(\d+)\u0000/g, (_, i) => codes[Number(i)]);
}

export function renderAnswerHtml(text, citations) {
  if (typeof text !== "string") return "";
  // The NUL character is our private placeholder marker: it can never come from the input.
  const clean = text.replace(/\u0000/g, "");
  if (!clean.trim()) return "";
  const byNumber = new Map();
  for (const c of Array.isArray(citations) ? citations : []) {
    if (c && Number.isInteger(c.n)) byNumber.set(c.n, c);
  }
  const html = [];
  let para = []; // lines of the open paragraph
  let list = null; // {tag, items} for the open list
  const flushPara = () => {
    if (para.length) html.push(`<p>${para.join("<br>")}</p>`);
    para = [];
  };
  const flushList = () => {
    if (list) html.push(`<${list.tag}>${list.items.map((i) => `<li>${i}</li>`).join("")}</${list.tag}>`);
    list = null;
  };
  for (const raw of clean.split(/\r?\n/)) {
    const line = escapeHtml(raw.trim());
    const bullet = /^[-*] +(.*)$/.exec(line);
    const numbered = /^\d+[.)] +(.*)$/.exec(line);
    if (!line) {
      flushPara();
      flushList();
    } else if (bullet || numbered) {
      flushPara();
      const tag = bullet ? "ul" : "ol";
      if (list && list.tag !== tag) flushList();
      list = list || { tag, items: [] };
      list.items.push(inline((bullet || numbered)[1], byNumber));
    } else {
      flushList();
      para.push(inline(line, byNumber));
    }
  }
  flushPara();
  flushList();
  return html.join("");
}
