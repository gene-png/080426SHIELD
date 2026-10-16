// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1129: the artifacts list proxy takes the client from `?client_id=` when
 * the request names one, so a workspace's document list is scoped to the
 * workspace, not to the active-client cookie another tab may have rewritten.
 * With no `client_id` it keeps the cookie (the client wizard's read names
 * none). The handler is CALLED, with `fetch` standing in for the api, and the
 * cookie names ANOTHER tenant throughout.
 */

const COOKIE_CLIENT = "00000000-0000-4000-8000-00000000c00c";
const WORKSPACE_CLIENT = "00000000-0000-4000-8000-000000001129";

vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({
    accessToken: "bearer-1129",
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

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
});

function sent(): { path: string; clientId: string | null } {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  return {
    path: new URL(url).pathname,
    clientId: new Headers(init.headers).get("X-Client-Id"),
  };
}

describe("GET /api/proxy/artifacts and the workspace's client (#1129)", () => {
  it("forwards ?client_id= as X-Client-Id, not the cookie", async () => {
    const { GET } = await import("./artifacts/route");
    const res = await GET(
      new Request(
        `http://localhost/api/proxy/artifacts?client_id=${WORKSPACE_CLIENT}`,
      ),
    );
    expect(res.status).toBe(200);
    expect(sent()).toEqual({
      path: "/artifacts",
      clientId: WORKSPACE_CLIENT,
    });
  });

  it("keeps the cookie when the request names no client", async () => {
    const { GET } = await import("./artifacts/route");
    const res = await GET(new Request("http://localhost/api/proxy/artifacts"));
    expect(res.status).toBe(200);
    expect(sent().clientId).toBe(COOKIE_CLIENT);
  });
});
