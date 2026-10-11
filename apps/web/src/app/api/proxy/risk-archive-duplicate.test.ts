// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #896 review B2: the proxy for the Risk-scoped archive route. The handler is
 * CALLED, with `fetch` standing in for the api, and both the upstream request
 * it makes and the response it builds are asserted.
 */

vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({
    accessToken: "bearer-896",
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
const SID = "00000000-0000-4000-8000-000000000896";

async function post(): Promise<Response> {
  const mod = await import("./risk/clients/[cid]/services/[sid]/archive/route");
  const handler = (mod as Record<string, unknown>).POST as
    ((req: Request, ctx: unknown) => Promise<Response>) | undefined;
  expect(handler, "the archive proxy must export POST").toBeTypeOf("function");
  return handler!(
    new Request(
      `http://localhost/api/proxy/risk/clients/${CID}/services/${SID}/archive`,
      { method: "POST" },
    ),
    { params: Promise.resolve({ cid: CID, sid: SID }) },
  );
}

describe("POST /api/proxy/risk/clients/:cid/services/:sid/archive (#896)", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("calls the api's Risk archive route and answers 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await post();
    expect(res.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith(`/risk/clients/${CID}/services/${SID}/archive`)).toBe(
      true,
    );
    expect(init.method).toBe("POST");
  });

  it("passes the api's typed refusal through with its status", async () => {
    const body = {
      error: {
        code: 409,
        reason: "service_not_in_duplicate_group",
        message: "x",
      },
    };
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 409,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const res = await post();
    expect(res.status).toBe(409);
    expect(await res.json()).toEqual(body);
  });
});
