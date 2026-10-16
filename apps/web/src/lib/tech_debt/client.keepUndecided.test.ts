import { afterEach, describe, expect, it, vi } from "vitest";

import { bulkSetDisposition } from "./client";

/**
 * TD-11 (for #1055): what "Keep {n} undecided rows" puts on the wire. The
 * component tests mock the client, so this pins the request itself. The key
 * comes from the API schema (`CapabilityDispositionBulkSet.only_if_undecided`).
 * #641's unflagged body is pinned, unchanged, by `client.test.ts`.
 */

const LIST_ID = "00000000-0000-4000-8000-0000000000aa";
const ITEM_IDS = ["00000000-0000-4000-8000-000000000001"];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("bulkSetDisposition, only_if_undecided (TD-11)", () => {
  it("sends the flag when it is set", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(JSON.stringify({ id: LIST_ID, items: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    );
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);

    await bulkSetDisposition(LIST_ID, ITEM_IDS, "keep", true);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit,
    ];
    expect(JSON.parse(init.body as string)).toStrictEqual({
      item_ids: ITEM_IDS,
      disposition: "keep",
      only_if_undecided: true,
    });
  });
});
