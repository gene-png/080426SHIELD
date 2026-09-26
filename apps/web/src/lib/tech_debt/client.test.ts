import { afterEach, describe, expect, it, vi } from "vitest";

import { bulkSetDisposition } from "./client";

/**
 * What `bulkSetDisposition` actually puts on the wire (#641, review round 1).
 *
 * Both component tests for the bulk bar mock this module, so they prove the
 * workspace CALLS it with the right arguments and nothing about the request it
 * then sends. A renamed key here (`items` for `item_ids`) would leave every one
 * of them green and turn each bulk action into a 422 against
 * `CapabilityDispositionBulkSet`.
 *
 * `jsonRequest` is module-private, so the seam is `fetch`, stubbed as a global
 * rather than mocked as a module. The expected keys come from the API schema
 * (`item_ids`, `disposition`), not from this client.
 */

const LIST_ID = "00000000-0000-4000-8000-0000000000aa";
const ITEM_IDS = [
  "00000000-0000-4000-8000-000000000001",
  "00000000-0000-4000-8000-000000000002",
];

function stubFetch() {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ id: LIST_ID, items: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
  return fetchMock;
}

function onlyCall(fetchMock: ReturnType<typeof stubFetch>) {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as unknown as [
    string,
    RequestInit,
  ];
  return { url, init, body: JSON.parse(init.body as string) as unknown };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("bulkSetDisposition", () => {
  it("POSTs item_ids and the disposition to the list's bulk endpoint", async () => {
    const fetchMock = stubFetch();

    await bulkSetDisposition(LIST_ID, ITEM_IDS, "cut");

    const { url, init, body } = onlyCall(fetchMock);
    expect(url).toBe(
      `/api/proxy/tech-debt/capability-lists/${LIST_ID}/items/disposition`,
    );
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe(
      "application/json",
    );
    expect(body).toStrictEqual({ item_ids: ITEM_IDS, disposition: "cut" });
  });

  it("sends disposition: null for Undecided, never omits the key", async () => {
    // The schema gives `disposition` no default, so a body WITHOUT the key is
    // a 422 rather than "return these rows to undecided". `toStrictEqual`
    // tells `null` from a missing key; `toEqual` would not.
    const fetchMock = stubFetch();

    await bulkSetDisposition(LIST_ID, ITEM_IDS, null);

    const { init, body } = onlyCall(fetchMock);
    expect(init.method).toBe("POST");
    expect(body).toStrictEqual({ item_ids: ITEM_IDS, disposition: null });
    expect(init.body as string).toContain('"disposition":null');
  });
});
