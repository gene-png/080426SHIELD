/**
 * T6: the old workspace URLs `/admin/services/{id}/{segment}` redirect to the
 * client-scoped frame. The service's client and kind come from the admin-only
 * service detail read, so a bookmark keeps working and lands on the right
 * client's frame.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  A,
  baseWorld,
  installFakeApi,
  NON_ADMIN_TOKEN,
  NotFoundSignal,
  RedirectSignal,
  type FakeCall,
} from "../../../clients/fake-api.testkit";

const session = vi.hoisted(() => ({
  value: { role: "admin", accessToken: "tok" } as Record<
    string,
    unknown
  > | null,
}));
vi.mock("@/lib/auth/options", () => ({ auth: async () => session.value }));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
}));
vi.mock("next/navigation", async () => {
  const kit = await import("../../../clients/fake-api.testkit");
  return {
    notFound: () => {
      throw new kit.NotFoundSignal();
    },
    redirect: (url: string) => {
      throw new kit.RedirectSignal(url);
    },
  };
});

import OldServicePage from "./page";

let calls: FakeCall[];

function call(id: string, segment: string) {
  return OldServicePage({ params: Promise.resolve({ id, segment }) });
}

beforeEach(() => {
  session.value = { role: "admin", accessToken: "tok" };
  const world = baseWorld();
  world.services.push(
    {
      id: "5e000000-0000-4000-8000-0000000000d1",
      client_id: A,
      kind: "attack_coverage",
      status: "draft",
      created_at: "2026-09-04T10:00:00Z",
    },
    {
      id: "5e000000-0000-4000-8000-0000000000e1",
      client_id: A,
      kind: "zero_trust_cisa",
      status: "draft",
      created_at: "2026-09-05T10:00:00Z",
    },
    {
      id: "5e000000-0000-4000-8000-0000000000f1",
      client_id: A,
      kind: "zero_trust_dod",
      status: "draft",
      created_at: "2026-09-06T10:00:00Z",
    },
  );
  calls = installFakeApi(world);
});

describe("old /admin/services/{id}/{segment} URLs", () => {
  it.each([
    ["5e000000-0000-4000-8000-0000000000a1", "tech-debt"],
    ["5e000000-0000-4000-8000-0000000000d1", "attack-coverage"],
    ["5e000000-0000-4000-8000-0000000000c1", "csf"],
    ["5e000000-0000-4000-8000-0000000000e1", "zero-trust-cisa"],
    ["5e000000-0000-4000-8000-0000000000f1", "zero-trust-dod"],
  ])("%s at /%s redirects to its client's Overview", async (id, segment) => {
    await expect(call(id, segment)).rejects.toEqual(
      new RedirectSignal(
        `/admin/clients/${A}/services/${segment}/overview?service=${id}`,
      ),
    );
  });

  it("sends a service opened under the wrong segment to its real kind", async () => {
    await expect(
      call("5e000000-0000-4000-8000-0000000000a1", "csf"),
    ).rejects.toEqual(
      new RedirectSignal(
        `/admin/clients/${A}/services/tech-debt/overview?service=5e000000-0000-4000-8000-0000000000a1`,
      ),
    );
  });

  it("finds an unknown service id not found", async () => {
    await expect(
      call("5e000000-0000-4000-8000-0000000000ff", "tech-debt"),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("finds a service id that is not a UUID not found (the API's 422)", async () => {
    await expect(call("nope", "tech-debt")).rejects.toBeInstanceOf(
      NotFoundSignal,
    );
  });

  it("finds an unknown segment not found without reading anything", async () => {
    await expect(
      call("5e000000-0000-4000-8000-0000000000a1", "settings"),
    ).rejects.toBeInstanceOf(NotFoundSignal);
    expect(calls).toEqual([]);
  });

  it("refuses when the API says the bearer is not an admin (403)", async () => {
    session.value = { role: "admin", accessToken: NON_ADMIN_TOKEN };
    await expect(
      call("5e000000-0000-4000-8000-0000000000a1", "tech-debt"),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("makes no API call for a client-role session", async () => {
    session.value = { role: "client", accessToken: "tok" };
    await expect(
      call("5e000000-0000-4000-8000-0000000000a1", "tech-debt"),
    ).rejects.toBeInstanceOf(NotFoundSignal);
    expect(calls).toEqual([]);
  });
});
