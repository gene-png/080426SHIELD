import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchAdminDeliverables } from "./deliverables";

/**
 * RR-2 (for #1121), design note §3.2: the fetcher names its client, and reads
 * a failure through `readFailureReason`. The #550 sentence is spelled out
 * once, as both the fixture's message and the absence needle.
 */
const OUTCOME_UNKNOWN =
  "We couldn't confirm whether this finished. It may still complete; check before trying again.";

function respond(status: number, body: unknown): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(body), {
          status,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchAdminDeliverables", () => {
  it("asks for the named client", async () => {
    respond(200, { items: [] });
    await fetchAdminDeliverables("client b/1");
    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toBe("/api/proxy/admin/deliverables?client_id=client%20b%2F1");
  });

  it("renders the server's sentence for an upstream 404", async () => {
    respond(404, { error: { code: 404, message: "No client with that id." } });
    await expect(fetchAdminDeliverables("c1")).rejects.toThrow(
      /^No client with that id\.$/,
    );
  });

  it("keeps the fallback for #550's 504, and never its sentence", async () => {
    respond(504, {
      error: {
        code: 504,
        reason: "upstream_outcome_unknown",
        message: OUTCOME_UNKNOWN,
      },
    });
    const err = await fetchAdminDeliverables("c1").catch((e: Error) => e);
    expect((err as Error).message).toBe("Failed to load deliverables (504).");
    expect((err as Error).message).not.toContain(OUTCOME_UNKNOWN);
  });

  it("keeps the fallback for the proxy's typed 400, which has no message", async () => {
    respond(400, { error: { code: 400, reason: "client_id_required" } });
    await expect(fetchAdminDeliverables("c1")).rejects.toThrow(
      /^Failed to load deliverables \(400\)\.$/,
    );
  });
});
