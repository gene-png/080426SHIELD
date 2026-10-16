/**
 * A fake FastAPI for the T6 frame's tests. It stands in at the NETWORK, under
 * the real `apiFetch`, so a test sees the exact `X-Client-Id` header a page
 * sends rather than the option a mock was handed. Each endpoint scopes the way
 * the real one does:
 * - `GET /admin/clients/{cid}`: 404 for an unknown client (admin-only route).
 * - `GET /intake/engagements`: the services of the `X-Client-Id` client
 *   (`current_client` + `Service.client_id == client.id`).
 * - `GET /services/{id}/stages`: 404 unless the service is the header client's.
 * - `GET /admin/services/{id}`: cross-tenant service detail, 404 if unknown.
 */
import { vi } from "vitest";

import type { FrameKind } from "@/components/service-shell/shellCopy";

export interface FakeService {
  id: string;
  client_id: string;
  kind: FrameKind;
  status: string;
  created_at: string;
}

export interface FakeWorld {
  clients: Record<
    string,
    { legal_name: string | null; dba_name: string | null }
  >;
  services: FakeService[];
  /** Status the stages endpoint answers with instead of 200. */
  stagesStatus?: number;
}

export interface FakeCall {
  path: string;
  clientId: string | null;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function header(init: RequestInit | undefined, name: string): string | null {
  const h = (init?.headers ?? {}) as Record<string, string>;
  return h[name] ?? null;
}

export function installFakeApi(world: FakeWorld): FakeCall[] {
  const calls: FakeCall[] = [];
  globalThis.fetch = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      const clientId = header(init, "X-Client-Id");
      calls.push({ path, clientId });
      if (!header(init, "Authorization")) return json({}, 401);

      let m = /^\/admin\/clients\/([^/]+)$/.exec(path);
      if (m) {
        const c = world.clients[decodeURIComponent(m[1])];
        if (!c) return json({ detail: "Client not found." }, 404);
        return json({ id: m[1], ...c, archived_at: null });
      }
      if (path === "/intake/engagements") {
        if (!clientId || !world.clients[clientId])
          return json({ detail: "No client." }, 400);
        return json(
          world.services
            .filter((s) => s.client_id === clientId)
            .map((s) => ({
              service_id: s.id,
              service_type: s.kind,
              title: `${s.kind} title`,
              status: s.status,
              assessment_status: null,
              withheld: false,
              created_at: s.created_at,
            })),
        );
      }
      m = /^\/services\/([^/]+)\/stages$/.exec(path);
      if (m) {
        const s = world.services.find((x) => x.id === m![1]);
        if (!s || s.client_id !== clientId)
          return json({ detail: "Service not found." }, 404);
        if (world.stagesStatus) return json({}, world.stagesStatus);
        return json({
          service_id: s.id,
          kind: s.kind,
          version: 2,
          stages: [
            { key: "prepare", state: "complete" },
            { key: "analyze", state: "current" },
            { key: "review", state: "pending" },
          ],
        });
      }
      m = /^\/admin\/services\/([^/]+)$/.exec(path);
      if (m) {
        const s = world.services.find((x) => x.id === m![1]);
        if (!s) return json({ detail: "Service not found." }, 404);
        return json({
          id: s.id,
          kind: s.kind,
          status: s.status,
          title: "t",
          client_id: s.client_id,
        });
      }
      throw new Error(`fake API: unexpected ${path}`);
    },
  ) as unknown as typeof fetch;
  return calls;
}

/** What `notFound()` and `redirect()` throw in these tests. */
export class NotFoundSignal extends Error {
  constructor() {
    super("NEXT_NOT_FOUND");
  }
}
export class RedirectSignal extends Error {
  constructor(public readonly url: string) {
    super(`NEXT_REDIRECT ${url}`);
  }
}

/** Two clients and their services, the world most tests start from. */
export const A = "client-a";
export const B = "client-b";
export function baseWorld(): FakeWorld {
  return {
    clients: {
      [A]: { legal_name: "Alpha Corp", dba_name: null },
      [B]: { legal_name: "Beta LLC", dba_name: null },
    },
    services: [
      {
        id: "td-a",
        client_id: A,
        kind: "tech_debt",
        status: "in_progress",
        created_at: "2026-09-01T10:00:00Z",
      },
      {
        id: "csf-a",
        client_id: A,
        kind: "nist_csf",
        status: "draft",
        created_at: "2026-09-02T10:00:00Z",
      },
      {
        id: "td-b",
        client_id: B,
        kind: "tech_debt",
        status: "in_progress",
        created_at: "2026-09-03T10:00:00Z",
      },
    ],
  };
}
