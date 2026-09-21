import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiFetch } from "./api";

/**
 * `apiFetch` had NO test (#318, from the #308 review).
 *
 * It is the choke point all six `app/api/proxy/*\/_proxy.ts` modules call, and
 * PR #308 certified the proxies' half of an invariant whose other half lives
 * here. The gap is not symmetric: a directory-derived test over the proxies
 * structurally cannot reach this file, so the branch #308 pinned becomes
 * unreachable the moment this one changes, and nothing goes red.
 *
 * Two branches here are load-bearing and neither was exercised by anything:
 *
 * 1. **204 returns `undefined`.** `admin/clients/[cid]/route.ts` and
 *    `admin/llm-key/route.ts` answer 204 off the back of it, and four DELETEs
 *    in `routes/admin.py` plus `POST /auth/logout` emit one. Delete this
 *    branch and `res.json()` throws on an empty body, so every proxy answers
 *    502 on a successful no-content response.
 * 2. **The body is read ONCE.** `res.json()` consumes the stream even when it
 *    throws, so a following `res.text()` raises "body stream already read" and
 *    THAT TypeError propagates in place of the typed error -- destroying the
 *    status and the correlation id at the moment they are needed. That is
 *    #174, fixed here and in ten other sites; nothing pinned it at this one.
 *
 * ## Why these use a REAL `Response`
 *
 * A hand-rolled `{ok, status, json, text}` mock has no single-use body. Under
 * one, a naive `res.json()`-then-`res.text()` implementation PASSES -- so the
 * test would be green against the exact defect it exists to catch, because the
 * fixture cannot express the property the fix is about.
 *
 * That is `CLAUDE.md`'s selector rule at the INPUT end, which it states as
 * "a fixture that builds an unreachable state is the same defect at the input
 * end" -- here inverted: this fixture would build a state the runtime cannot
 * produce (a body readable twice) and would therefore prove nothing about the
 * runtime. Quoted by its actual wording rather than a paraphrase of mine: an
 * earlier version of this comment attributed a sentence to that file which is
 * not in it, and a correct constraint with a false citation is worse than an
 * unexplained one -- a reader told to verify what they read checks the quote,
 * fails to find it, and may discard the rule.
 *
 * `Response` is the producer's own type and enforces the real semantics.
 */

// A COOKIE IS PRESENT, and that is what makes the `clientId: ""` test mean
// anything. With the cookie mocked absent, "no X-Client-Id header" was true
// whether or not `""` was handled correctly -- so the ONE mutation that test
// exists to catch survived it green:
//
//     if (opts.clientId !== undefined)   ->   if (opts.clientId)
//
// which is precisely the implementation its own comment names. Under the
// mutation `clientId: ""` falls through to the cookie, finds nothing, sets no
// header, and the assertion passes. Three admin proxies pass `clientId: ""`
// for exactly this reason ("cross-tenant by design"), so the live consequence
// is an admin's active-tenant cookie re-scoping a cross-tenant DELETE.
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => ({ value: "cookie-tenant" }) }),
}));

function mockFetch(response: Response): ReturnType<typeof vi.fn> {
  const f = vi.fn(async () => response);
  vi.stubGlobal("fetch", f);
  return f;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("apiFetch", () => {
  it("returns undefined for 204 rather than parsing an empty body", async () => {
    mockFetch(new Response(null, { status: 204 }));
    await expect(
      apiFetch("/admin/llm-key", { method: "DELETE" }),
    ).resolves.toBeUndefined();
  });

  it("parses a 200 body", async () => {
    mockFetch(
      new Response(JSON.stringify({ id: "abc" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    await expect(
      apiFetch<{ id: string }>("/admin/services/1"),
    ).resolves.toEqual({
      id: "abc",
    });
  });

  it("throws ApiError carrying the status, correlation id and parsed payload", async () => {
    mockFetch(
      new Response(
        JSON.stringify({ error: { reason: "nope", message: "No." } }),
        {
          status: 409,
          headers: {
            "Content-Type": "application/json",
            "X-Request-ID": "corr-1",
          },
        },
      ),
    );

    const err = await apiFetch("/zt/answers/1", { method: "PATCH" }).then(
      () => null,
      (e: unknown) => e,
    );

    expect(err).toBeInstanceOf(ApiError);
    const api = err as ApiError;
    expect(api.status).toBe(409);
    expect(api.correlationId).toBe("corr-1");
    expect(api.payload).toEqual({ error: { reason: "nope", message: "No." } });
  });

  it("survives a NON-JSON error body instead of throwing a body-stream error", async () => {
    // THE #174 ASSERTION, and the one the real `Response` exists for. A crashed
    // dev server answers an HTML page; a naive implementation calls
    // `res.json()`, it rejects AND consumes the stream, the fallback
    // `res.text()` throws "body stream already read", and a TypeError
    // propagates with the status and correlation id gone.
    mockFetch(
      new Response("<html><body>502 Bad Gateway</body></html>", {
        status: 502,
        headers: { "X-Request-ID": "corr-2" },
      }),
    );

    const err = await apiFetch("/risk/registers/1").then(
      () => null,
      (e: unknown) => e,
    );

    expect(
      err,
      "a non-JSON error body must still produce a typed ApiError; a TypeError here means the body was read twice",
    ).toBeInstanceOf(ApiError);
    const api = err as ApiError;
    expect(api.status).toBe(502);
    expect(api.correlationId).toBe("corr-2");
    // The raw text survives as the payload rather than being discarded.
    expect(api.payload).toContain("502 Bad Gateway");
  });

  it("survives an EMPTY error body", async () => {
    // The other shape a crashed upstream returns, and the one where
    // `JSON.parse("")` throws. Distinct from the HTML case because an empty
    // string is falsy and an over-eager `payload = raw || something` would
    // quietly substitute.
    mockFetch(new Response("", { status: 500 }));

    const err = await apiFetch("/csf/assessments/1").then(
      () => null,
      (e: unknown) => e,
    );

    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
    expect((err as ApiError).payload).toBe("");
  });

  it("omits X-Client-Id when clientId is the empty string", async () => {
    // The admin proxies pass `clientId: ""` deliberately -- they are
    // cross-tenant by design and a forwarded header would scope them. An
    // implementation treating "" as "fall back to the cookie" would
    // silently re-scope every admin call.
    const f = mockFetch(new Response(null, { status: 204 }));
    await apiFetch("/admin/clients/1", { method: "DELETE", clientId: "" });

    const headers = (f.mock.calls[0][1] as RequestInit).headers as Record<
      string,
      string
    >;
    expect(Object.keys(headers)).not.toContain("X-Client-Id");
  });

  it("falls back to the cookie when no clientId is given", async () => {
    // The branch the absent-cookie mock made untestable. This is the tenant
    // scoping the whole multi-tenant product rests on, and nothing exercised
    // it.
    const f = mockFetch(new Response(JSON.stringify({}), { status: 200 }));
    await apiFetch("/clients/me/dashboard");

    const headers = (f.mock.calls[0][1] as RequestInit).headers as Record<
      string,
      string
    >;
    expect(headers["X-Client-Id"]).toBe("cookie-tenant");
  });

  it("rejects an unparseable 200 rather than returning undefined", async () => {
    // THE THIRD EXIT, and the one the proxies' safety argument rests on.
    // Each `_proxy.ts` reasons: "`apiFetch` has exactly three exits ... an
    // unparseable 200 throws in `res.json()` before reaching here. That makes
    // the swallow LATENT rather than live." Nothing asserted the third.
    //
    // The mutation that survived: wrapping the success parse in
    // `try { ... } catch { return undefined }` as a plausible hardening. Then
    // every proxy reads `result === undefined` as 204 and answers the browser
    // 204 No Content over a broken 200 -- #173 resurrected through the door
    // #308 closed, with `proxies-never-synthesise-an-empty-result.test.ts`
    // still green because it only reads proxy SOURCE TEXT.
    mockFetch(new Response("<html>not json</html>", { status: 200 }));

    await expect(apiFetch("/csf/catalog")).rejects.toThrow();
  });

  it("sends the bearer and an explicit client id when given", async () => {
    const f = mockFetch(new Response(JSON.stringify({}), { status: 200 }));
    await apiFetch("/clients/1/risk/dashboard", {
      bearer: "tok",
      clientId: "cid-9",
    });

    const headers = (f.mock.calls[0][1] as RequestInit).headers as Record<
      string,
      string
    >;
    expect(headers.Authorization).toBe("Bearer tok");
    expect(headers["X-Client-Id"]).toBe("cid-9");
  });
});
