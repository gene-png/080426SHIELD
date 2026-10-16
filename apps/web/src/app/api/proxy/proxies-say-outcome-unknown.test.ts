// @vitest-environment node
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * A proxy that cannot see the api's answer must say the outcome is UNKNOWN
 * (#550, plan of record v3.1 section 2).
 *
 * When `fetch` rejects (Node's 300 s headers timeout, a reset, a refused
 * connection) the api may already have done the work: #550 measured an
 * extraction that kept running after the caller gave up, wrote its `llm_calls`
 * row and created the draft list. The proxies answered an untyped 502 "call
 * failed", the natural response to which is a retry that egresses the client's
 * data again. They must answer 504 with the typed reason instead.
 *
 * ## Through the surface, not the source
 *
 * Every handler is CALLED, with `fetch` rejecting the way Node's does, and the
 * response it builds is what is asserted. A source grep for the 502 branch is
 * what the plan rejected: `proxy/artifacts/route.ts` has its `fetch` outside any
 * `try`, so it had no 502 branch to find and threw instead.
 *
 * ## Derived, not listed
 *
 * The set is every `route.ts` and `_proxy.ts` under `app/api/proxy`, read off
 * the directory, so a new route is covered the day it is added. The helpers
 * are exercised through the routes that import them.
 */

// Spelled out, not imported from the builder: the plan of record is the spec,
// and a test reading the builder's own constants agrees with it by construction.
const REASON = "upstream_outcome_unknown";
const MESSAGE =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

// #1130: a READ that got no answer cannot "still complete", so a proxy whose
// upstream call was a GET says it could not load instead. Spelled out for the
// same reason as above. PLACEHOLDER copy, pending the advisor's verbatim ruling.
const READ_REASON = "upstream_read_failed";
const READ_MESSAGE =
  "SHIELD's server didn't answer, so this couldn't be loaded. Reload the page to try again.";

/**
 * Which body the proxy owes, decided by the method of the upstream call it
 * made (never by the handler's name): a GET handler that writes upstream still
 * owes #550's, and a write handler's read owes the read body.
 */
function owedFor(): {
  kind: "read" | "write";
  error: { code: number; reason: string; message: string };
} {
  const init = fetchMock.mock.calls.at(-1)?.[1] as RequestInit | undefined;
  const upstreamMethod = (init?.method ?? "GET").toUpperCase();
  const read = upstreamMethod === "GET" || upstreamMethod === "HEAD";
  owedKinds.add(read ? "read" : "write");
  return read
    ? {
        kind: "read",
        error: { code: 504, reason: READ_REASON, message: READ_MESSAGE },
      }
    : { kind: "write", error: { code: 504, reason: REASON, message: MESSAGE } };
}

/** Both kinds must be exercised, or one half of #1130 is tested by nothing. */
const owedKinds = new Set<"read" | "write">();

const PROXY_ROOT = join(process.cwd(), "src/app/api/proxy");

function routeFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...routeFiles(p));
    else if (entry === "route.ts" || entry === "_proxy.ts") out.push(p);
  }
  return out.sort();
}

const FILES = routeFiles(PROXY_ROOT);
const ROUTES = FILES.filter((p) => p.endsWith("route.ts"));
const label = (p: string) =>
  p.slice(p.indexOf("api/proxy")).replace(/\\/g, "/");

const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"] as const;
type Method = (typeof METHODS)[number];

/** The handlers a route file declares, read from its source. */
function declaredMethods(path: string): Method[] {
  const src = readFileSync(path, "utf8");
  return METHODS.filter((m) =>
    new RegExp(
      String.raw`export\s+(async\s+function\s+|const\s+|function\s+)${m}\b`,
    ).test(src),
  );
}

const HANDLERS = ROUTES.flatMap((p) =>
  declaredMethods(p).map((m) => [`${m} ${label(p)}`, p, m] as const),
);

// RR-2 (#1121): some routes branch on a `client_id` query parameter, so every
// handler is called both WITH and WITHOUT one, and each branch is judged by
// what it answers. Without it a route must either reach upstream, as before,
// or refuse with the typed 400 `client_id_required` before any upstream call.
// Which routes do which is read from the response, never from a list. Both
// request builders carry the same choice, including the multipart fallback
// `call()` uses for a route that refuses a JSON body, so a "with client_id"
// case is never quietly sent without one.
const CLIENT_ID = "00000000-0000-4000-8000-000000000550";
const CASES = HANDLERS.flatMap(
  ([name, path, method]) =>
    [
      [`${name} (with client_id)`, path, method, true],
      [`${name} (without client_id)`, path, method, false],
    ] as const,
);

/** The typed refusal a route gives when it needs `client_id` and has none. */
async function refusedForMissingClientId(
  name: string,
  res: Response,
): Promise<void> {
  expect(
    fetchMock.mock.calls.length,
    `${name} refused without calling upstream, so it must be the client_id refusal`,
  ).toBe(0);
  const body = (await res.json()) as { error?: { reason?: unknown } };
  expect(
    { status: res.status, reason: body.error?.reason },
    `${name} made no upstream call: only the typed client_id refusal may do that`,
  ).toEqual({ status: 400, reason: "client_id_required" });
}

// An admin session with a bearer: the most permissive caller, so every route
// gets as far as its upstream call.
vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({
    accessToken: "bearer-550",
    role: "admin",
    user: { email: "admin@example.com", role: "admin" },
  })),
}));
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: () => undefined })),
  headers: vi.fn(async () => new Headers()),
}));

/** What Node's `fetch` throws when the api never sends its headers. */
function headersTimeout(): TypeError {
  const cause = Object.assign(new Error("Headers Timeout Error"), {
    code: "UND_ERR_HEADERS_TIMEOUT",
  });
  return new TypeError("fetch failed", { cause });
}

const fetchMock = vi.fn(async (..._args: unknown[]): Promise<Response> => {
  throw headersTimeout();
});
const realFetch = globalThis.fetch;
globalThis.fetch = fetchMock as unknown as typeof fetch;
afterAll(() => {
  globalThis.fetch = realFetch;
});

// Every dynamic segment gets the same well-formed id: a route that validates
// its params must still reach its upstream call.
const PARAMS = new Proxy(
  {},
  {
    get: (_t, key) =>
      typeof key === "string"
        ? "00000000-0000-4000-8000-000000000550"
        : undefined,
  },
);

function jsonRequest(method: Method, withClientId: boolean): Request {
  const query = withClientId ? `?limit=10&client_id=${CLIENT_ID}` : "?limit=10";
  return new Request(`http://localhost/api/proxy/x${query}`, {
    method,
    ...(method === "GET"
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        }),
  });
}

function multipartRequest(method: Method, withClientId: boolean): Request {
  const form = new FormData();
  form.append("file", new Blob(["a,b\n1,2\n"], { type: "text/csv" }), "x.csv");
  const query = withClientId ? `?client_id=${CLIENT_ID}` : "";
  return new Request(`http://localhost/api/proxy/x${query}`, {
    method,
    body: form,
  });
}

type Handler = (req: Request, ctx: unknown) => Promise<Response>;

async function call(
  path: string,
  method: Method,
  withClientId: boolean,
): Promise<Response> {
  const mod = (await import(/* @vite-ignore */ path)) as Record<
    string,
    unknown
  >;
  const handler = mod[method];
  expect(typeof handler, `${method} is declared but not exported`).toBe(
    "function",
  );
  const ctx = { params: Promise.resolve(PARAMS) };
  let res = await (handler as Handler)(jsonRequest(method, withClientId), ctx);
  if (fetchMock.mock.calls.length === 0 && method !== "GET") {
    // A multipart route refuses a JSON body before it calls upstream.
    res = await (handler as Handler)(
      multipartRequest(method, withClientId),
      ctx,
    );
  }
  return res;
}

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => {
    throw headersTimeout();
  });
  vi.spyOn(console, "error").mockImplementation(() => undefined);
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
});

describe("proxies say the outcome is unknown when they cannot see the api's answer (#550)", () => {
  it("selects the proxy sources at all", () => {
    // A glob that selects nothing would pass every per-route case below by
    // having none. The count is printed so a run says what it covered.
    console.info(
      `[#550] ${FILES.length} files selected (${ROUTES.length} route.ts), ${HANDLERS.length} handlers`,
    );
    expect(ROUTES.length).toBeGreaterThan(0);
    expect(FILES.length).toBeGreaterThan(ROUTES.length);
    expect(HANDLERS.length).toBeGreaterThanOrEqual(ROUTES.length);
  });

  it("finds at least one handler in EVERY selected route file", () => {
    // A total can hide a file that contributes nothing: a handler declared in
    // a spelling `declaredMethods` does not read would drop that route from
    // every case below while the total still clears the bar (review of #752,
    // advisory 5). Per file, so the gap is named.
    const unread = ROUTES.filter((p) => declaredMethods(p).length === 0).map(
      label,
    );
    expect(unread, "route files with no handler this test can call").toEqual(
      [],
    );
  });

  it.each(CASES)(
    "%s answers a rejected fetch with the typed 504",
    async (name, path, method, withClientId) => {
      const res = await call(path, method, withClientId);
      if (!withClientId && fetchMock.mock.calls.length === 0) {
        await refusedForMissingClientId(name, res);
        return;
      }
      expect(
        fetchMock.mock.calls.length,
        `${name} never called upstream, so this test cannot judge it`,
      ).toBeGreaterThan(0);
      const owed = owedFor();
      const body = (await res.json()) as {
        error?: { code?: unknown; reason?: unknown; message?: unknown };
      };
      expect(
        { status: res.status, error: body.error },
        owed.kind === "write"
          ? `${name} must answer 504 upstream_outcome_unknown: the api may have finished`
          : `${name} read upstream, so it must answer 504 upstream_read_failed (#1130)`,
      ).toEqual({ status: 504, error: owed.error });
    },
  );

  it.each(CASES)(
    "%s answers a response whose BODY never arrives with the typed 504",
    async (name, path, method, withClientId) => {
      // The api's headers arrived and the connection then reset mid-body: the
      // status line says nothing about whether the work finished, and the
      // body that would have said so is gone. Every route reads the body of a
      // refusal itself, so a non-2xx status reaches that read on every route
      // (review of #752, finding 3: the download route read it outside any
      // try, an unhandled throw).
      fetchMock.mockImplementation(
        async () =>
          new Response(
            new ReadableStream({
              start(controller) {
                controller.error(
                  new TypeError("terminated", {
                    cause: Object.assign(new Error("other side closed"), {
                      code: "UND_ERR_SOCKET",
                    }),
                  }),
                );
              },
            }),
            { status: 409, headers: { "Content-Type": "application/json" } },
          ),
      );
      const res = await call(path, method, withClientId);
      if (!withClientId && fetchMock.mock.calls.length === 0) {
        await refusedForMissingClientId(name, res);
        return;
      }
      expect(fetchMock.mock.calls.length, name).toBeGreaterThan(0);
      const owed = owedFor();
      const body = (await res.json()) as {
        error?: { code?: unknown; reason?: unknown; message?: unknown };
      };
      expect(
        { status: res.status, error: body.error },
        `${name} must answer 504 ${owed.error.reason} when the body never arrives`,
      ).toEqual({ status: 504, error: owed.error });
    },
  );

  it("judged both a read and a write (#1130)", () => {
    // Runs after the cases above (vitest keeps file order). A run that judged
    // only reads, or only writes, would prove one half of #1130.
    expect([...owedKinds].sort()).toEqual(["read", "write"]);
  });

  it.each(CASES)(
    "%s passes an answer the api DID send through unchanged",
    async (name, path, method, withClientId) => {
      // The other half: only a missing answer is "unknown". A refusal the api
      // sent is its own typed outcome and must reach the browser as sent.
      const refusal = {
        error: { code: 409, reason: "some_refusal", message: "Refused." },
      };
      fetchMock.mockImplementation(
        async () =>
          new Response(JSON.stringify(refusal), {
            status: 409,
            headers: { "Content-Type": "application/json" },
          }),
      );
      const res = await call(path, method, withClientId);
      if (!withClientId && fetchMock.mock.calls.length === 0) {
        await refusedForMissingClientId(name, res);
        return;
      }
      expect(fetchMock.mock.calls.length, name).toBeGreaterThan(0);
      expect({ status: res.status, body: await res.json() }, name).toEqual({
        status: 409,
        body: refusal,
      });
    },
  );
});
