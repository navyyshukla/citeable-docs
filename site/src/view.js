// Turns an API result into a plain view model, and checks the question box. No DOM here, so
// it can be tested with node. Links are kept only when they are plain https URLs.
import { renderAnswerHtml } from "./render.js";

const isHttps = (u) => typeof u === "string" && u.startsWith("https://") && !/[\s"'<>`\\]/.test(u);
const list = (x) => (Array.isArray(x) ? x : []);
const text = (x) => (typeof x === "string" ? x : "");

const UNKNOWN = {
  label: "Something unexpected came back",
  bodyHtml: "",
  sources: [],
  closest: [],
  showFeedback: false,
};

export function resultView(result) {
  if (!result || typeof result !== "object") return { ...UNKNOWN };
  const citations = list(result.citations).filter((c) => c && isHttps(c.url));
  const sources = citations.map((c) => ({ n: c.n, title: text(c.title), url: c.url }));
  const closest = list(result.closest)
    .filter((c) => c && isHttps(c.url))
    .map((c) => ({ title: text(c.title), url: c.url }));
  if (result.status === "answered") {
    return {
      label: "Answered from the docs",
      bodyHtml: renderAnswerHtml(text(result.text), citations),
      sources,
      closest: [],
      showFeedback: true,
    };
  }
  if (result.status === "abstained") {
    return {
      label: "I couldn't find this in the docs",
      bodyHtml: renderAnswerHtml(text(result.text), []),
      sources: [],
      closest,
      showFeedback: false,
    };
  }
  return { ...UNKNOWN };
}

// Same rule as the server: trim, then count characters (not UTF-16 units).
export function questionState(value, max) {
  const trimmed = typeof value === "string" ? value.trim() : "";
  const count = [...trimmed].length;
  const tooLong = count > max;
  return { count, tooLong, canAsk: count > 0 && !tooLong };
}

// Which banner is showing. A later message of one kind must not remove a different kind: the
// health check hides only its own "waking" banner, never the "invite not saved" warning.
export function createBannerState() {
  let state = null;
  return {
    show(message, kind = "info") { state = { message, kind }; },
    hide(onlyKind) { if (!onlyKind || (state && state.kind === onlyKind)) state = null; },
    current() { return state; },
  };
}

// Which screen to show. No token means the invite screen, even if a conversation was started
// earlier, so a forgotten device never shows a stale conversation.
export function pageState({ hasToken, started }) {
  if (!hasToken) return "invite";
  return started ? "chatting" : "welcome";
}
