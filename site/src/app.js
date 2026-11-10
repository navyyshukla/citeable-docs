// Page wiring. The logic that can be tested without a browser lives in token.js, api.js,
// view.js and render.js. Server text is always put in with textContent; the only innerHTML is the
// output of the safe renderer (render.js).
import { createApi } from "./api.js";
import { loadToken, saveToken, forgetToken } from "./token.js";
import { resultView, questionState } from "./view.js";

const $ = (id) => document.getElementById(id);
const config = JSON.parse($("page-config").textContent);
const MAX = config.max_question_chars;
const api = createApi({ baseUrl: config.api_base_url });

function getStorage() {
  try {
    return window.localStorage;
  } catch {
    return null; // blocked storage: the page still works for this visit
  }
}
const storage = getStorage();

const box = $("question");
const askButton = $("ask");
const counter = $("counter");
const banner = $("banner");
let token = null;
let busy = false;
let bannerKind = null;

function showBanner(message, kind = "info") {
  banner.textContent = message;
  banner.className = kind === "error" ? "error" : "";
  banner.hidden = false;
  bannerKind = kind;
}
function hideBanner(onlyKind) {
  if (onlyKind && bannerKind !== onlyKind) return;
  banner.hidden = true;
  bannerKind = null;
}

function updateControls() {
  const st = questionState(box.value, MAX);
  counter.textContent = `${st.count}/${MAX}`;
  counter.className = st.tooLong ? "over" : "";
  askButton.disabled = busy || !token || !st.canAsk;
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function link(url, text) {
  const a = el("a", null, text);
  a.href = url; // view.js has already kept only plain https URLs
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

function feedbackBlock(requestId) {
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
      await api.feedback(token, requestId, rating, text);
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

function addCard(question, result) {
  const v = resultView(result);
  const kind = result && (result.status === "answered" || result.status === "abstained")
    ? result.status : "unknown";
  const card = el("article", "card");
  card.append(el("p", "q", `You asked: ${question}`), el("span", `status ${kind}`, v.label));
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
  if (v.showFeedback && result.request_id) card.append(feedbackBlock(result.request_id));
  $("answers").prepend(card);
  if (result && result.docs_version) {
    const date = result.last_updated ? `, last updated ${result.last_updated}` : "";
    $("docs-info").textContent = `Docs version ${result.docs_version}${date}.`;
  }
}

async function ask() {
  const question = box.value.trim();
  if (busy || !questionState(question, MAX).canAsk || !token) return;
  busy = true;
  updateControls();
  showBanner("Looking through the docs…");
  const slow = setTimeout(() => showBanner(
    "Looking through the docs… the server may be waking up, which can take up to 30 seconds."), 3000);
  try {
    const result = await api.ask(token, question);
    addCard(question, result);
    box.value = "";
    hideBanner();
  } catch (err) {
    showBanner(err.message, "error"); // the question stays in the box so nothing is lost
  } finally {
    clearTimeout(slow);
    busy = false;
    updateControls();
  }
}

function showNoInvite(message) {
  const notice = $("invite-missing");
  if (message) notice.textContent = message;
  notice.hidden = false;
  $("ask-section").hidden = true;
}

function wakeCheck() {
  let answered = false;
  const timer = setTimeout(() => {
    if (!answered) showBanner("Waking the server up, up to 30 seconds…");
  }, 3000);
  api.health().then(() => {
    answered = true;
    clearTimeout(timer);
    hideBanner("info");
  });
}

// ---- start-up ----
const loaded = loadToken(storage, location.hash);
token = loaded.token;
if (loaded.fromLink) {
  if (saveToken(storage, token)) {
    history.replaceState(null, "", location.pathname + location.search); // token out of the address bar
  } else {
    showBanner("Your browser would not save the invite link. Keep this link: you will need it again.");
  }
}
if (!token) {
  showNoInvite(location.hash.startsWith("#t=")
    ? "This invite link looks cut off or damaged. Ask the person who sent it for a new one." : undefined);
} else {
  wakeCheck();
}

box.addEventListener("input", updateControls);
box.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) $("ask-form").requestSubmit();
});
$("ask-form").addEventListener("submit", (e) => {
  e.preventDefault();
  ask();
});
document.querySelector(".starters").addEventListener("click", (e) => {
  const q = e.target instanceof Element ? e.target.closest("[data-question]") : null;
  if (!q) return;
  box.value = q.dataset.question; // fills the box only: the visitor decides when to send
  updateControls();
  box.focus();
});
$("forget").addEventListener("click", (e) => {
  e.preventDefault();
  forgetToken(storage);
  token = null;
  history.replaceState(null, "", location.pathname + location.search);
  $("answers").replaceChildren();
  hideBanner();
  showNoInvite("This device has forgotten your invite. Open your invite link again to continue.");
  updateControls();
});
updateControls();
