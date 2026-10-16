// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * #1130, through the real chain rather than a hand-built body: the admin
 * deliverables proxy gets no answer from the api (Node's `fetch` rejects), and
 * the page's fetcher reads the proxy's real response. A read must say it could
 * not load, never #550's "It may still complete". Both sentences are spelled
 * out, not imported, so the test cannot agree with the code by construction.
 */
const READ_FAILED =
  "SHIELD's server didn't answer, so this couldn't be loaded. Reload the page to try again.";
const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({ accessToken: "bearer-1130", role: "admin" })),
}));
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: () => undefined })),
  headers: vi.fn(async () => new Headers()),
}));

import { GET } from "@/app/api/proxy/admin/deliverables/route";

import { fetchAdminDeliverables } from "./deliverables";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("admin deliverables, when the api never answers (#1130)", () => {
  it("shows the read message, not #550's sentence", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    // 1. The proxy, with the api unreachable.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("fetch failed", {
          cause: Object.assign(new Error("Headers Timeout Error"), {
            code: "UND_ERR_HEADERS_TIMEOUT",
          }),
        });
      }),
    );
    const proxied = await GET(
      new Request(
        "http://localhost/api/proxy/admin/deliverables?client_id=00000000-0000-4000-8000-000000001130",
      ),
    );
    expect(proxied.status).toBe(504);
    const body = await proxied.text();

    // 2. The page's fetcher, handed exactly what the proxy answered.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(body, {
            status: proxied.status,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    const err = await fetchAdminDeliverables(
      "00000000-0000-4000-8000-000000001130",
    ).catch((e: Error) => e);
    expect(err).toBeInstanceOf(Error);
    expect((err as Error).message).toBe(READ_FAILED);
    expect((err as Error).message).not.toContain(OUTCOME_UNKNOWN);
  });
});
