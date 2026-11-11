// Builds the pieces of the conversation: the visitor's bubble and the answer card. Server text is
// always put in with textContent; the only innerHTML is the output of the safe renderer
// (render.js, through view.js).
import { resultView } from "./view.js";

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function link(url, text) {
  const a = el("a", null, text);
  a.href = url; // view.js has already kept only plain https URLs
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

export function buildUserBubble(question) {
  return el("div", "msg-user", question);
}

// The "thinking" line shown in the feed while an answer is on its way: three pulsing dots (pure
// CSS, so it stays smooth) and a short honest label. The dots are decoration only.
export function buildThinking(text) {
  const wrap = el("div", "thinking");
  wrap.setAttribute("role", "status");
  wrap.setAttribute("aria-live", "polite");
  const dots = el("span", "dots");
  dots.setAttribute("aria-hidden", "true");
  dots.append(el("i"), el("i"), el("i"));
  wrap.append(dots, el("span", "thinking-text", text));
  return wrap;
}

export function setThinkingText(node, text) {
  const t = node.querySelector(".thinking-text");
  if (t) t.textContent = text;
}

function feedbackBlock(requestId, { api, getToken }) {
  const wrap = el("div", "feedback");
  wrap.append(el("span", null, "Was this helpful?"));
  const yes = el("button", null, "Yes, helpful");
  const no = el("button", null, "No");
  const comment = el("textarea");
  comment.rows = 2;
  comment.placeholder = "What was wrong? (optional)";
  comment.hidden = true;
  const send = el("button", null, "Send");
  send.hidden = true;
  const note = el("span", "thanks");
  yes.type = no.type = send.type = "button";

  async function submit(rating, text) {
    yes.disabled = no.disabled = send.disabled = true;
    try {
      await api.feedback(getToken(), requestId, rating, text);
      wrap.replaceChildren(el("span", "thanks", "Thanks, your feedback was saved."));
    } catch (err) {
      note.textContent = err.message;
      yes.disabled = no.disabled = send.disabled = false;
    }
  }
  yes.addEventListener("click", () => submit(1));
  no.addEventListener("click", () => {
    comment.hidden = send.hidden = false;
    no.disabled = true;
    comment.focus();
  });
  send.addEventListener("click", () => submit(-1, comment.value.trim() || undefined));
  wrap.append(yes, no, comment, send, note);
  return wrap;
}

export function buildAnswerCard(result, deps) {
  const v = resultView(result);
  const kind = result && (result.status === "answered" || result.status === "abstained")
    ? result.status : "unknown";
  const card = el("article", "card");
  card.append(el("span", `status ${kind}`, v.label));
  const body = el("div", "body");
  body.innerHTML = v.bodyHtml; // output of the safe renderer only
  card.append(body);
  if (v.sources.length) {
    card.append(el("p", "thanks", "Sources in the docs:"));
    const ul = el("ul", "sources");
    for (const s of v.sources) {
      const li = el("li");
      li.append(link(s.url, `[${s.n}] ${s.title}`));
      ul.append(li);
    }
    card.append(ul);
  }
  if (v.closest.length) {
    card.append(el("p", "thanks", "Closest pages in the docs:"));
    const ul = el("ul", "sources");
    for (const s of v.closest) {
      const li = el("li");
      li.append(link(s.url, s.title));
      ul.append(li);
    }
    card.append(ul);
  }
  const start = kind === "abstained" && deps && Array.isArray(deps.startLinks) ? deps.startLinks : [];
  if (start.length) {
    card.append(el("p", "thanks", "New to VisiData? Start here:"));
    const row = el("div", "links links-card");
    for (const l of start) row.append(link(l.url, l.text));
    card.append(row);
  }
  if (v.showFeedback && result.request_id) card.append(feedbackBlock(result.request_id, deps));
  return card;
}
