// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1129 and #1262: the artifacts proxy takes the client from `?client_id=`
 * when the request names one, for the list (GET) AND the upload (POST), so a
 * workspace's documents are listed and FILED under the workspace's client,
 * not the active-client cookie another tab may have rewritten. With no
 * `client_id` it keeps the cookie (the client wizard names none); an EMPTY one
 * is refused, as the download proxy does. The handlers are CALLED, with
 * `fetch` standing in for the api, and the cookie names ANOTHER tenant
 * throughout.
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

  it("refuses an EMPTY ?client_id= rather than falling back to the cookie", async () => {
    const { GET } = await import("./artifacts/route");
    const res = await GET(
      new Request("http://localhost/api/proxy/artifacts?client_id="),
    );
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the cookie when the request names no client", async () => {
    const { GET } = await import("./artifacts/route");
    const res = await GET(new Request("http://localhost/api/proxy/artifacts"));
    expect(res.status).toBe(200);
    expect(sent().clientId).toBe(COOKIE_CLIENT);
  });
});

function uploadRequest(query: string): Request {
  const form = new FormData();
  form.append("file", new Blob(["host,os"], { type: "text/csv" }), "a.csv");
  return new Request(`http://localhost/api/proxy/artifacts${query}`, {
    method: "POST",
    body: form,
  });
}

describe("POST /api/proxy/artifacts files under the workspace's client (#1262)", () => {
  it("forwards ?client_id= as X-Client-Id, not the cookie", async () => {
    const { POST } = await import("./artifacts/route");
    const res = await POST(uploadRequest(`?client_id=${WORKSPACE_CLIENT}`));
    expect(res.status).toBe(200);
    expect(sent()).toEqual({
      path: "/artifacts",
      clientId: WORKSPACE_CLIENT,
    });
  });

  it("keeps the cookie when the request names no client", async () => {
    const { POST } = await import("./artifacts/route");
    await POST(uploadRequest(""));
    expect(sent().clientId).toBe(COOKIE_CLIENT);
  });

  it("refuses an EMPTY ?client_id=", async () => {
    const { POST } = await import("./artifacts/route");
    const res = await POST(uploadRequest("?client_id="));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
