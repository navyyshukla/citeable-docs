// Page wiring. The logic that can be tested without a browser lives in token.js, api.js,
// view.js, input.js, theme.js and render.js; cards.js builds the conversation pieces. Server text is always put in with textContent (see cards.js).
import { createApi } from "./api.js";
import { loadToken, saveToken, forgetToken } from "./token.js";
import { questionState, createBannerState, pageState } from "./view.js";
import { buildUserBubble, buildAnswerCard } from "./cards.js";
import { enterAction, growHeight, scrollBehavior, isTouchDevice } from "./input.js";
import { readTheme, saveTheme, effectiveTheme, nextTheme } from "./theme.js";

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
let started = false; // true once the first answer card is on the page
const bannerState = createBannerState();

function renderBanner() {
  const b = bannerState.current();
  banner.hidden = !b;
  if (!b) return;
  banner.textContent = b.message;
  banner.className = b.kind === "error" ? "error" : "";
}
function showBanner(message, kind = "info") {
  bannerState.show(message, kind);
  renderBanner();
}
function hideBanner(onlyKind) {
  bannerState.hide(onlyKind);
  renderBanner();
}

function updateControls() {
  const st = questionState(box.value, MAX);
  counter.textContent = `${st.count}/${MAX}`;
  counter.className = st.tooLong ? "over" : "";
  askButton.disabled = busy || !token || !st.canAsk;
}

function setState() {
  document.body.dataset.state = pageState({ hasToken: !!token, started });
}

const darkQuery = () => window.matchMedia("(prefers-color-scheme: dark)").matches;
const themeButton = $("theme");
function paintThemeButton() {
  const dark = effectiveTheme(readTheme(storage), darkQuery()) === "dark";
  themeButton.textContent = dark ? "☀️" : "🌙";
  themeButton.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
}

// The box grows with the text up to about 8 lines, then scrolls.
const BOX_MIN = 24;
const BOX_MAX = 192;
function resizeBox() {
  box.style.height = "auto";
  const h = growHeight(box.scrollHeight, BOX_MIN, BOX_MAX);
  box.style.height = `${h}px`;
  box.style.overflowY = box.scrollHeight > BOX_MAX ? "auto" : "hidden";
}

function addExchange(question, result) {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const card = buildAnswerCard(result, { api, getToken: () => token });
  $("answers").append(buildUserBubble(question), card);
  started = true;
  setState();
  card.scrollIntoView({ behavior: scrollBehavior(reduced), block: "start" });
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
    addExchange(question, result);
    box.value = "";
    resizeBox();
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
  setState();
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
    showBanner("Your browser would not save the invite link. Keep this link: you will need it again.", "warn");
  }
}
if (!token) {
  showNoInvite(location.hash.startsWith("#t=")
    ? "This invite link looks cut off or damaged. Ask the person who sent it for a new one." : undefined);
} else {
  wakeCheck();
}
setState();
paintThemeButton();

box.addEventListener("input", () => {
  updateControls();
  resizeBox();
});
box.addEventListener("keydown", (e) => {
  if (enterAction(e, isTouchDevice(window.matchMedia)) === "send") {
    e.preventDefault();
    $("ask-form").requestSubmit();
  }
});
themeButton.addEventListener("click", () => {
  const next = nextTheme(readTheme(storage), darkQuery());
  document.documentElement.dataset.theme = next;
  saveTheme(storage, next);
  paintThemeButton();
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
  resizeBox();
  box.focus();
});
$("forget").addEventListener("click", (e) => {
  e.preventDefault();
  forgetToken(storage);
  token = null;
  started = false;
  history.replaceState(null, "", location.pathname + location.search);
  $("answers").replaceChildren();
  hideBanner();
  showNoInvite("This device has forgotten your invite. Open your invite link again to continue.");
  updateControls();
});
updateControls();
