// @vitest-environment node
import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * #1262, the `/intake` residual (answered on #1262, 6219252390). The wizard now
 * names the client it loaded (`?client_id=`), and these proxies must forward
 * THAT client as X-Client-Id rather than the shared active-client cookie,
 * which another tab may have rewritten. An empty value is refused before any
 * upstream call. With no parameter, the cookie as before: the first load, and
 * a client-role user, whom the api pins to their own client anyway.
 */

const CLIENT_A = "00000000-0000-4000-8000-0000000000a1";
const COOKIE_B = "00000000-0000-4000-8000-0000000000b2";

vi.mock("@/lib/auth/options", () => ({
  auth: vi.fn(async () => ({
    accessToken: "bearer-1262",
    role: "admin",
    user: { email: "admin@example.com", role: "admin" },
  })),
}));
vi.mock("next/headers", () => ({
  cookies: vi.fn(async () => ({
    get: (name: string) =>
      name === "shield_active_client_id" ? { value: COOKIE_B } : undefined,
  })),
  headers: vi.fn(async () => new Headers()),
}));

const fetchMock = vi.fn(
  async (..._args: unknown[]): Promise<Response> =>
    new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
);
const realFetch = globalThis.fetch;
globalThis.fetch = fetchMock as unknown as typeof fetch;
afterAll(() => {
  globalThis.fetch = realFetch;
});

beforeEach(() => {
  fetchMock.mockClear();
});

function sentClient(): string | null {
  expect(fetchMock).toHaveBeenCalledTimes(1);
  const init = fetchMock.mock.calls[0][1] as RequestInit;
  return new Headers(init.headers).get("X-Client-Id");
}

type Handler = (req: Request) => Promise<Response>;

const CASES = [
  "GET /intake",
  "PATCH /intake",
  "POST /intake/submit",
  "GET /artifacts",
  "POST /artifacts",
] as const;

async function call(name: (typeof CASES)[number], query: string) {
  const intake = await import("./route");
  const submit = await import("./submit/route");
  const artifacts = await import("../artifacts/route");
  const url = (path: string) => `http://localhost${path}${query}`;
  const json = (method: string, path: string) =>
    new Request(url(path), {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client: { city: "Arlington" } }),
    });
  switch (name) {
    case "GET /intake":
      return (intake.GET as Handler)(new Request(url("/api/proxy/intake")));
    case "PATCH /intake":
      return intake.PATCH(json("PATCH", "/api/proxy/intake"));
    case "POST /intake/submit":
      return submit.POST(json("POST", "/api/proxy/intake/submit"));
    case "GET /artifacts":
      return (artifacts.GET as Handler)(
        new Request(url("/api/proxy/artifacts")),
      );
    case "POST /artifacts": {
      const form = new FormData();
      form.append("file", new Blob(["x"]), "x.txt");
      return artifacts.POST(
        new Request(url("/api/proxy/artifacts"), {
          method: "POST",
          body: form,
        }),
      );
    }
  }
}

describe("the intake proxies forward the client the wizard names (#1262)", () => {
  it.each(CASES)("%s: a named client wins over the cookie", async (name) => {
    const res = await call(name, `?client_id=${CLIENT_A}`);
    expect(res.status).toBe(200);
    expect(sentClient()).toBe(CLIENT_A);
  });

  it.each(CASES)(
    "%s: with no parameter, the cookie as before",
    async (name) => {
      const res = await call(name, "");
      expect(res.status).toBe(200);
      expect(sentClient()).toBe(COOKIE_B);
    },
  );

  it.each(CASES)(
    "%s: an empty client_id is refused upstream of any call",
    async (name) => {
      const res = await call(name, "?client_id=");
      expect(fetchMock).not.toHaveBeenCalled();
      expect(res.status).toBe(400);
      const body = (await res.json()) as { error?: { reason?: unknown } };
      expect(body.error?.reason).toBe("client_id_required");
    },
  );
});
