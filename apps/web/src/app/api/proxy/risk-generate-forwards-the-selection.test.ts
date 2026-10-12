// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * RR-1 (for #1122), design note §3.1: the generate proxy forwards the
 * admin's selection as parsed, forwards an empty body as none, and refuses an
 * unparseable one with copy 10 BEFORE any upstream call. The handler is
 * CALLED, with `fetch` standing in for the api. Before RR-1 it forwarded
 * `{method: "POST"}` alone, so a selection never reached the api.
 */

vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({
    accessToken: "bearer-1122",
    role: "admin",
    user: { email: "admin@example.com", role: "admin" },
  })),
}));
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({ get: () => undefined })),
  headers: vi.fn(async () => new Headers()),
}));

const fetchMock = vi.fn();
const realFetch = globalThis.fetch;
globalThis.fetch = fetchMock as unknown as typeof fetch;
afterAll(() => {
  globalThis.fetch = realFetch;
});

const CID = "00000000-0000-4000-8000-0000000000c1";

async function post(body: string | undefined): Promise<Response> {
  const mod = await import("./risk/clients/[cid]/register/generate/route");
  const handler = (mod as Record<string, unknown>).POST as
    ((req: Request, ctx: unknown) => Promise<Response>) | undefined;
  expect(handler, "the generate proxy must export POST").toBeTypeOf("function");
  return handler!(
    new Request(
      `http://localhost/api/proxy/risk/clients/${CID}/register/generate`,
      {
        method: "POST",
        body,
        headers: { "Content-Type": "application/json" },
      },
    ),
    { params: Promise.resolve({ cid: CID }) },
  );
}

function upstreamOk(): void {
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ id: "r1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("POST /api/proxy/risk/clients/:cid/register/generate (RR-1)", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("forwards the selection to the api's generate route, as sent", async () => {
    upstreamOk();
    const include = { include: { csf: false, zero_trust: "dod_ztra" } };
    const res = await post(JSON.stringify(include));
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith(`/risk/clients/${CID}/register/generate`)).toBe(true);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual(include);
  });

  it.each([
    ["no body", undefined],
    ["an empty body", ""],
    ["whitespace", "  \n"],
  ])(
    "forwards %s as no body (the api's absent-body default)",
    async (_n, b) => {
      upstreamOk();
      const res = await post(b);
      expect(res.status).toBe(200);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
      expect(init.body ?? undefined).toBeUndefined();
    },
  );

  it("refuses an unparseable body with copy 10, and calls nothing upstream", async () => {
    const res = await post("{not json");
    expect(res.status).toBe(400);
    expect(await res.json()).toEqual({
      error: {
        code: 400,
        reason: "risk_selection_unreadable",
        message:
          "The services to include could not be read. Reload the page and choose them again.",
      },
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
