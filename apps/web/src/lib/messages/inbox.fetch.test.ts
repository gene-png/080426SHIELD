import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchInbox } from "./client";

/** RR-2 (for #1121), design note §3.2: the inbox read names its client. */
afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchInbox", () => {
  it("asks for the named client", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(JSON.stringify({ threads: [], unread_total: 0 }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
      ),
    );
    await fetchInbox("client b/1");
    const [url] = vi.mocked(fetch).mock.calls[0] as [string];
    expect(url).toBe("/api/proxy/messages/inbox?client_id=client%20b%2F1");
  });
});
