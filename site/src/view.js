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

// Which banner is showing. Each kind keeps its own slot, so a later message of one kind never
// erases another: the "waking" note or a failed question cannot wipe out the "invite not saved"
// warning, which comes back when they go away. When several are set, the most important shows
// (error, then warn, then info).
const PRIORITY = ["error", "warn", "info"];
export function createBannerState() {
  const slots = {};
  return {
    show(message, kind = "info") { slots[kind] = { message, kind }; },
    hide(onlyKind) {
      if (onlyKind) delete slots[onlyKind];
      else for (const k of Object.keys(slots)) delete slots[k];
    },
    current() {
      for (const k of PRIORITY) if (slots[k]) return slots[k];
      return Object.values(slots)[0] || null;
    },
  };
}

// Which screen to show. No token means the invite screen, even if a conversation was started
// earlier, so a forgotten device never shows a stale conversation.
export function pageState({ hasToken, started }) {
  if (!hasToken) return "invite";
  return started ? "chatting" : "welcome";
}

// Links offered under a refused question ("New to VisiData? Start here"). They come from the page
// config; only labelled plain-https links are kept.
export function startLinks(list) {
  if (!Array.isArray(list)) return [];
  return list.filter((x) => x && typeof x.text === "string" && x.text !== "" && isHttps(x.url))
    .map((x) => ({ text: x.text, url: x.url }));
}

// What the "thinking" line says while a question is being answered. The label is honest (no
// invented stages); after 3 seconds it says why it may be slow.
export function thinkingText(elapsedMs) {
  return elapsedMs >= 3000
    ? "Still working… the server may be waking up, which can take up to 30 seconds."
    : "Searching the docs…";
}

// The fixed cards ("what is VisiData?", "what can you do?"). The API says only which one; the
// text comes from the page's own config and is always shown as plain text.
const CARD_KINDS = ["about", "help"];

export function cardKind(result) {
  if (!result || typeof result !== "object" || result.status !== "card") return null;
  return CARD_KINDS.includes(result.kind) ? result.kind : null;
}

export function cardView(kind, cards) {
  if (!CARD_KINDS.includes(kind) || !cards || typeof cards !== "object") return null;
  const c = cards[kind];
  if (!c || typeof c !== "object") return null;
  const label = text(c.label);
  const paragraphs = list(c.paragraphs).filter((p) => typeof p === "string" && p.trim() !== "");
  if (label === "" || paragraphs.length === 0) return null;
  return {
    label,
    paragraphs,
    links: startLinks(c.links),
    examples: list(c.examples).filter((q) => typeof q === "string" && q.trim() !== ""),
  };
}

// The model's short reply inside the Help card: plain paragraphs, at most three, each cut at 600
// characters. The page shows them with textContent only, so nothing here is ever HTML.
export function helpParagraphs(value) {
  if (typeof value !== "string") return [];
  return value.split(/\n\s*\n/).map((p) => p.trim()).filter((p) => p !== "")
    .slice(0, 3).map((p) => p.slice(0, 600));
}
