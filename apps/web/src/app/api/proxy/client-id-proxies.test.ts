// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * RR-2 (for #1121), design note §3.2 and §3.2a. The three proxies the twin
 * admin pages call take the client from `?client_id=`, never from the cookie
 * when it is given. The handlers are CALLED, with `fetch` standing in for the
 * api, and the cookie names ANOTHER tenant throughout, so a handler that
 * reads it is caught by the header it sends.
 */

const COOKIE_CLIENT = "00000000-0000-4000-8000-00000000c00c";
const PICKED = "00000000-0000-4000-8000-0000000b1121";

vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({
    accessToken: "bearer-1121",
    role: "admin",
    user: { email: "admin@example.com", role: "admin" },
  })),
}));
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) =>
      name === "shield_active_client_id" ? { value: COOKIE_CLIENT } : undefined,
  })),
  headers: vi.fn(async () => new Headers()),
}));

const fetchMock = vi.fn();
const realFetch = globalThis.fetch;
globalThis.fetch = fetchMock as unknown as typeof fetch;
afterAll(() => {
  globalThis.fetch = realFetch;
});

function sentClientId(): string | null {
  const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return new Headers(init.headers).get("X-Client-Id");
}

type Handler = (req: Request, ctx?: unknown) => Promise<Response>;

const LIST_PROXIES: Array<[string, string, () => Promise<Handler>]> = [
  [
    "admin/deliverables",
    "/admin/deliverables",
    async () => (await import("./admin/deliverables/route")).GET as Handler,
  ],
  [
    "messages/inbox",
    "/messages/inbox",
    async () => (await import("./messages/inbox/route")).GET as Handler,
  ],
];

beforeEach(() => {
  fetchMock.mockReset();
});

describe.each(LIST_PROXIES)(
  "GET /api/proxy/%s takes the client from ?client_id=",
  (path, upstream, load) => {
    it("forwards client_id as X-Client-Id, and ignores the cookie", async () => {
      fetchMock.mockResolvedValue(
        new Response(JSON.stringify({ items: [], threads: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      const GET = await load();
      const res = await GET(
        new Request(`http://localhost/api/proxy/${path}?client_id=${PICKED}`),
      );
      expect(res.status).toBe(200);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(new URL(url).pathname).toBe(upstream);
      expect(sentClientId()).toBe(PICKED);
    });

    it.each([
      ["absent", ""],
      ["empty", "?client_id="],
    ])(
      "refuses a %s client_id with the typed 400, before any upstream call",
      async (_label, query) => {
        const error = vi
          .spyOn(console, "error")
          .mockImplementation(() => undefined);
        const GET = await load();
        const res = await GET(
          new Request(`http://localhost/api/proxy/${path}${query}`),
        );
        expect(res.status).toBe(400);
        expect(await res.json()).toEqual({
          error: { code: 400, reason: "client_id_required" },
        });
        // Never the cookie's tenant: no upstream call at all.
        expect(fetchMock).not.toHaveBeenCalled();
        expect(
          error.mock.calls.some((args) =>
            String(args[0]).includes("proxy.client_id_missing"),
          ),
        ).toBe(true);
        error.mockRestore();
      },
    );
  },
);

describe("GET /api/proxy/artifacts/:id/download (§3.2a)", () => {
  const ARTIFACT = "00000000-0000-4000-8000-0000000a7e1d";

  async function download(query: string): Promise<Response> {
    const { GET } = await import("./artifacts/[id]/download/route");
    return GET(
      new Request(
        `http://localhost/api/proxy/artifacts/${ARTIFACT}/download${query}`,
      ),
      { params: Promise.resolve({ id: ARTIFACT }) },
    );
  }

  function ok(): Response {
    return new Response("file-bytes", {
      status: 200,
      headers: {
        "Content-Type": "application/pdf",
        "Content-Disposition": 'attachment; filename="b.pdf"',
      },
    });
  }

  it("sends client_id, not the cookie's tenant, when client_id is given", async () => {
    fetchMock.mockResolvedValue(ok());
    const res = await download(`?client_id=${PICKED}`);
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(sentClientId()).toBe(PICKED);
  });

  it("refuses an EMPTY client_id with the typed 400, before any upstream call", async () => {
    const error = vi
      .spyOn(console, "error")
      .mockImplementation(() => undefined);
    const res = await download("?client_id=");
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({
      error: { code: 400, reason: "client_id_required" },
    });
    expect(fetchMock).not.toHaveBeenCalled();
    error.mockRestore();
  });

  it("forwards the cookie, as today, when client_id is absent (its eight other callers)", async () => {
    fetchMock.mockResolvedValue(ok());
    const res = await download("");
    expect(res.status).toBe(200);
    expect(sentClientId()).toBe(COOKIE_CLIENT);
  });
});
