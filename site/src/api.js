// API client. Every failure becomes an ApiError with a plain-language message (status is null
// for network failures and timeouts). The default timeout (90 s) covers the measured 22.9 s cold start plus a slow answer (about 26 s).

const NETWORK = "Couldn't reach the server. Check your connection and try again.";
// A timeout is not a dead connection: the server may still be finishing the answer.
const TIMEOUT = "This took too long. The server may still be finishing; wait a minute, then try again.";

export function describeError(status, body) {
  const text = body && typeof body.error === "string" ? body.error : null;
  if (status === null || status === undefined) return NETWORK;
  if (status === 401) {
    return "This invite link isn't valid or was withdrawn. Ask the person who sent it for a new one.";
  }
  if (status === 429) return text || "You've reached today's limit. Try again later.";
  if (status === 503) return "The assistant is busy. Try again in a minute.";
  if (status === 400 && text) return text;
  return "Something went wrong. Please try again.";
}

export class ApiError extends Error {
  constructor(status, body, message) {
    super(message || describeError(status, body));
    this.status = status;
    this.body = body;
  }
}

export function createApi({ baseUrl, fetchFn, timeoutMs = 90000 }) {
  const base = String(baseUrl).replace(/\/+$/, "");
  const doFetch = fetchFn || ((...args) => globalThis.fetch(...args));

  async function request(path, init) {
    const ctrl = new AbortController();
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => {
        ctrl.abort();
        reject(new ApiError(null, null, TIMEOUT));
      }, timeoutMs);
    });
    const work = (async () => {
      const res = await doFetch(base + path, { ...init, signal: ctrl.signal });
      const body = await res.json().catch(() => null);
      return { res, body };
    })();
    try {
      // The race also covers a fetch that ignores the abort signal, and a body that never ends.
      const { res, body } = await Promise.race([work, timeout]);
      if (!res.ok) throw new ApiError(res.status, body);
      if (body === null) {
        throw new ApiError(res.status, null, "The server sent a reply this page could not read. Try again.");
      }
      return body;
    } catch (e) {
      if (e instanceof ApiError) throw e;
      throw new ApiError(null, null);
    } finally {
      clearTimeout(timer);
      work.catch(() => {}); // a late failure after the timeout must not become unhandled
    }
  }

  const post = (token, path, payload) =>
    request(path, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

  return {
    async health() {
      try {
        await request("/health", { method: "GET" });
        return true;
      } catch {
        return false;
      }
    },
    ask: (token, question) => post(token, "/ask", { question }),
    async feedback(token, requestId, rating, comment) {
      await post(token, "/feedback", { request_id: requestId, rating, comment: comment ?? null });
    },
  };
}
