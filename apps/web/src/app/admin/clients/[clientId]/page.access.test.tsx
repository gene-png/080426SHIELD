/**
 * T6: the client overview and the client layout (the rail). Both take the
 * client from the URL, check it server-side, and read its services with that
 * client's id rather than the active-client cookie's.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  A,
  baseWorld,
  installFakeApi,
  NotFoundSignal,
  type FakeCall,
} from "../fake-api.testkit";
import type { FrameKind } from "@/components/service-shell/shellCopy";

const session = vi.hoisted(() => ({
  value: { role: "admin", accessToken: "tok" } as Record<
    string,
    unknown
  > | null,
}));
vi.mock("@/lib/auth/options", () => ({ auth: async () => session.value }));
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "shield_active_client_id"
        ? { value: "c1000000-0000-4000-8000-00000000000b" }
        : undefined,
  }),
}));
vi.mock("next/navigation", async () => {
  const kit = await import("../fake-api.testkit");
  return {
    notFound: () => {
      throw new kit.NotFoundSignal();
    },
    redirect: (url: string) => {
      throw new kit.RedirectSignal(url);
    },
    usePathname: () => `/admin/clients/c1000000-0000-4000-8000-00000000000a`,
    useSearchParams: () => new URLSearchParams(),
    useRouter: () => ({ push: vi.fn() }),
  };
});
// The rail's picker loads the client list in the browser; not under test here.
vi.mock("@/components/service-shell/ClientNavPicker", () => ({
  ClientNavPicker: () => null,
}));

import ClientLayout from "./layout";
import ClientOverviewPage from "./page";

let calls: FakeCall[];

beforeEach(() => {
  session.value = { role: "admin", accessToken: "tok" };
  calls = installFakeApi(baseWorld());
});

function overview(clientId: string) {
  return ClientOverviewPage({ params: Promise.resolve({ clientId }) });
}

describe("client overview page", () => {
  it("lists the client's open services and the Risk Register", async () => {
    render(await overview(A));
    expect(
      screen.getByRole("heading", { level: 1, name: "Alpha Corp" }),
    ).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Services" });
    expect(
      within(list)
        .getByRole("link", { name: "Technical Debt Review" })
        .getAttribute("href"),
    ).toBe(
      `/admin/clients/${A}/services/tech-debt/overview?service=5e000000-0000-4000-8000-0000000000a1`,
    );
    expect(within(list).getByText("In progress")).toBeInTheDocument();
    expect(
      within(list).getByRole("link", { name: "NIST CSF 2.0" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Risk Register" }).getAttribute("href"),
    ).toBe(`/admin/clients/${A}/services/risk-register`);
    // Client B's service is not shown.
    expect(
      screen.getAllByRole("link", { name: "Technical Debt Review" }),
    ).toHaveLength(1);
  });

  it("lists archived services apart, still reachable", async () => {
    const world = baseWorld();
    world.services[0].status = "archived";
    calls = installFakeApi(world);
    render(await overview(A));
    const archived = screen.getByRole("list", { name: "Archived services" });
    expect(
      within(archived).getByRole("link", { name: "Technical Debt Review" }),
    ).toBeInTheDocument();
    const open = screen.getByRole("list", { name: "Services" });
    expect(
      within(open).queryByRole("link", { name: "Technical Debt Review" }),
    ).toBeNull();
  });

  it("says when no service is open, with the intake queue link", async () => {
    const world = baseWorld();
    world.services = [];
    calls = installFakeApi(world);
    render(await overview(A));
    expect(
      screen.getByText("No services are open for this client yet."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open the intake queue" }),
    ).toHaveAttribute("href", `/admin/queue/${A}`);
  });

  it("leaves out a consultation, which has no workspace", async () => {
    const world = baseWorld();
    world.services.push({
      id: "5e000000-0000-4000-8000-0000000000aa",
      client_id: A,
      kind: "consultation" as FrameKind,
      status: "draft",
      created_at: "2026-09-05T10:00:00Z",
    });
    calls = installFakeApi(world);
    render(await overview(A));
    const list = screen.getByRole("list", { name: "Services" });
    expect(
      within(list).getByRole("link", { name: "NIST CSF 2.0" }),
    ).toBeInTheDocument();
    expect(within(list).getAllByRole("link")).toHaveLength(2);
  });

  it("refuses loudly a service kind the frame does not know", async () => {
    const world = baseWorld();
    world.services.push({
      id: "5e000000-0000-4000-8000-0000000000ab",
      client_id: A,
      kind: "some_new_kind" as FrameKind,
      status: "draft",
      created_at: "2026-09-05T10:00:00Z",
    });
    calls = installFakeApi(world);
    await expect(overview(A)).rejects.toThrow(
      'unknown service kind "some_new_kind"',
    );
  });

  it("refuses an unknown client", async () => {
    await expect(
      overview("c1000000-0000-4000-8000-0000000000ff"),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses a client id that is not a UUID (the API's 422)", async () => {
    await expect(overview("not-a-uuid")).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("makes no API call for a client-role session", async () => {
    session.value = { role: "client", accessToken: "tok" };
    await expect(overview(A)).rejects.toBeInstanceOf(NotFoundSignal);
    expect(calls).toEqual([]);
  });

  it("reads the services with the URL's client, never the cookie's", async () => {
    render(await overview(A));
    const scoped = calls.filter((c) => c.clientId !== null);
    expect(scoped.map((c) => c.path)).toContain("/intake/engagements");
    for (const c of scoped) expect(c.clientId).toBe(A);
  });
});

describe("client layout (the rail)", () => {
  function layout(clientId: string) {
    return ClientLayout({
      params: Promise.resolve({ clientId }),
      children: <p>section body</p>,
    });
  }

  it("renders the rail beside the page", async () => {
    render(await layout(A));
    const rail = screen.getByRole("navigation", { name: "Client services" });
    expect(
      within(rail).getByRole("link", { name: "Technical Debt Review" }),
    ).toBeInTheDocument();
    expect(screen.getByText("section body")).toBeInTheDocument();
  });

  it("refuses a client id that is not a UUID (the API's 422)", async () => {
    await expect(layout("not-a-uuid")).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses an unknown client before rendering anything", async () => {
    await expect(
      layout("c1000000-0000-4000-8000-0000000000ff"),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("makes no API call for a client-role session", async () => {
    session.value = { role: "client", accessToken: "tok" };
    await expect(layout(A)).rejects.toBeInstanceOf(NotFoundSignal);
    expect(calls).toEqual([]);
  });
});
