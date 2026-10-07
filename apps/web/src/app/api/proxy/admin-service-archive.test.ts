// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #896: the web proxy for a service gains DELETE, the archive the Risk
 * Register's duplicate banner calls. Until #896 it exported GET only, so the
 * API's `DELETE /admin/services/{id}` had no screen caller.
 *
 * The handler is CALLED, with `fetch` standing in for the api, and both the
 * upstream request it makes and the response it builds are asserted.
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

const ID = "00000000-0000-4000-8000-000000000896";

async function del(): Promise<Response> {
  const mod = await import("./admin/services/[id]/route");
  const handler = (mod as Record<string, unknown>).DELETE as
    ((req: Request, ctx: unknown) => Promise<Response>) | undefined;
  expect(handler, "the service proxy must export DELETE").toBeTypeOf(
    "function",
  );
  return handler!(
    new Request(`http://localhost/api/proxy/admin/services/${ID}`, {
      method: "DELETE",
    }),
    { params: Promise.resolve({ id: ID }) },
  );
}

describe("DELETE /api/proxy/admin/services/:id (#896)", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("archives through the api's DELETE and answers 204", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await del();
    expect(res.status).toBe(204);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url.endsWith(`/admin/services/${ID}`)).toBe(true);
    expect(init.method).toBe("DELETE");
    expect((init.headers as Record<string, string>).Authorization).toBe(
      "Bearer bearer-896",
    );
  });

  it("passes the api's refusal through with its status", async () => {
    const body = { error: { code: 404, message: "Service not found." } };
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(body), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const res = await del();
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual(body);
  });
});
