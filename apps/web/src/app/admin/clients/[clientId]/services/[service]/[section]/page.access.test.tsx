/**
 * T6: the section page is where the frame decides WHICH service's workspace to
 * mount. The URL is not authorization: every guard here is tested through the
 * page, against a fake API under the real `apiFetch`, so deleting a guard turns
 * a named test red.
 */
import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  A,
  B,
  baseWorld,
  installFakeApi,
  NotFoundSignal,
  RedirectSignal,
  type FakeCall,
} from "../../../../fake-api.testkit";

const session = vi.hoisted(() => ({
  value: { role: "admin", accessToken: "tok" } as Record<
    string,
    unknown
  > | null,
}));
vi.mock("@/lib/auth/options", () => ({ auth: async () => session.value }));
// The active-client cookie names client B in every test: the page must never
// use it.
vi.mock("next/headers", () => ({
  cookies: async () => ({
    get: (name: string) =>
      name === "shield_active_client_id"
        ? { value: "c1000000-0000-4000-8000-00000000000b" }
        : undefined,
  }),
}));
vi.mock("next/navigation", async () => {
  const kit = await import("../../../../fake-api.testkit");
  return {
    notFound: () => {
      throw new kit.NotFoundSignal();
    },
    redirect: (url: string) => {
      throw new kit.RedirectSignal(url);
    },
  };
});
vi.mock("@/components/admin/EnsureActiveClient", () => ({
  EnsureActiveClient: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));
vi.mock("@/components/admin/TechDebtWorkspace", () => ({
  TechDebtWorkspace: (p: { serviceId: string }) => (
    <div data-testid="workspace">tech_debt {p.serviceId}</div>
  ),
}));
vi.mock("@/components/admin/attack/AttackWorkspace", () => ({
  AttackWorkspace: (p: { serviceId: string }) => (
    <div data-testid="workspace">attack {p.serviceId}</div>
  ),
}));
vi.mock("@/components/admin/csf/CsfWorkspace", () => ({
  CsfWorkspace: (p: { serviceId: string }) => (
    <div data-testid="workspace">csf {p.serviceId}</div>
  ),
}));
vi.mock("@/components/admin/zt/ZtWorkspace", () => ({
  ZtWorkspace: (p: { serviceId: string; framework: string }) => (
    <div data-testid="workspace">
      zt {p.framework} {p.serviceId}
    </div>
  ),
}));

import SectionPage from "./page";

let calls: FakeCall[];

function call(
  clientId: string,
  service: string,
  section: string,
  query: Record<string, string> = {},
) {
  return SectionPage({
    params: Promise.resolve({ clientId, service, section }),
    searchParams: Promise.resolve(query),
  });
}

async function renderSection(...args: Parameters<typeof call>): Promise<void> {
  render(await call(...args));
}

beforeEach(() => {
  session.value = { role: "admin", accessToken: "tok" };
  calls = installFakeApi(baseWorld());
});

describe("section page: renders the right workspace", () => {
  it("mounts client A's Tech Debt workspace under the section bar", async () => {
    await renderSection(A, "tech-debt", "review", {
      service: "5e000000-0000-4000-8000-0000000000a1",
    });
    expect(screen.getByTestId("workspace")).toHaveTextContent(
      "tech_debt 5e000000-0000-4000-8000-0000000000a1",
    );
    const bar = screen.getByRole("navigation", { name: "Service sections" });
    expect(within(bar).getByRole("link", { name: "Review" })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      within(bar).getByRole("link", { name: "Inputs" }).getAttribute("href"),
    ).toBe(
      `/admin/clients/${A}/services/tech-debt/inputs?service=5e000000-0000-4000-8000-0000000000a1`,
    );
    expect(within(bar).getAllByRole("link")).toHaveLength(9);
  });

  it("omits Inputs for CSF (page-plan decision 1)", async () => {
    await renderSection(A, "csf", "ai-draft", {
      service: "5e000000-0000-4000-8000-0000000000c1",
    });
    const bar = screen.getByRole("navigation", { name: "Service sections" });
    expect(within(bar).queryByRole("link", { name: "Inputs" })).toBeNull();
    expect(within(bar).getAllByRole("link")).toHaveLength(8);
  });

  it("shows the service header from the stages read", async () => {
    await renderSection(A, "tech-debt", "overview", {
      service: "5e000000-0000-4000-8000-0000000000a1",
    });
    expect(screen.getByTestId("service-header-version")).toHaveTextContent(
      "v2",
    );
    expect(screen.getByTestId("service-header-status")).toHaveTextContent(
      "In progress",
    );
    expect(screen.getByTestId("service-header-stage")).toHaveTextContent(
      "Analyze",
    );
    expect(
      screen.getByRole("link", { name: "Technical Debt Review" }),
    ).toHaveAttribute(
      "href",
      `/admin/clients/${A}/services/tech-debt/overview?service=5e000000-0000-4000-8000-0000000000a1`,
    );
  });

  it("still renders the workspace when the header read fails", async () => {
    calls = installFakeApi({ ...baseWorld(), stagesStatus: 500 });
    const err = vi.spyOn(console, "error").mockImplementation(() => {});
    await renderSection(A, "tech-debt", "overview", {
      service: "5e000000-0000-4000-8000-0000000000a1",
    });
    expect(
      screen.getByText("The version, status and stage could not be loaded."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("service-header-version")).toBeNull();
    expect(screen.getByTestId("workspace")).toBeInTheDocument();
    expect(err).toHaveBeenCalled();
  });

  it("opens an archived service named by id (old links keep working)", async () => {
    const world = baseWorld();
    world.services[0].status = "archived";
    calls = installFakeApi(world);
    await renderSection(A, "tech-debt", "overview", {
      service: "5e000000-0000-4000-8000-0000000000a1",
    });
    expect(screen.getByTestId("workspace")).toHaveTextContent(
      "5e000000-0000-4000-8000-0000000000a1",
    );
  });
});

describe("section page: access (the URL is not authorization)", () => {
  it("refuses client B's service under client A's URL", async () => {
    await expect(
      call(A, "tech-debt", "overview", {
        service: "5e000000-0000-4000-8000-0000000000b1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses a service whose kind is not the URL's", async () => {
    await expect(
      call(A, "csf", "overview", {
        service: "5e000000-0000-4000-8000-0000000000a1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses Inputs for CSF", async () => {
    await expect(
      call(A, "csf", "inputs", {
        service: "5e000000-0000-4000-8000-0000000000c1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses an unknown section and an unknown service slug", async () => {
    await expect(
      call(A, "tech-debt", "settings", {
        service: "5e000000-0000-4000-8000-0000000000a1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
    await expect(
      call(A, "bogus", "overview", {
        service: "5e000000-0000-4000-8000-0000000000a1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses a client id that is not a UUID (the API's 422)", async () => {
    await expect(
      call("not-a-uuid", "tech-debt", "overview", {
        service: "5e000000-0000-4000-8000-0000000000a1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("refuses an unknown client", async () => {
    await expect(
      call("c1000000-0000-4000-8000-0000000000ff", "tech-debt", "overview", {
        service: "5e000000-0000-4000-8000-0000000000a1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
  });

  it("makes no API call for a client-role session", async () => {
    session.value = { role: "client", accessToken: "tok" };
    await expect(
      call(A, "tech-debt", "overview", {
        service: "5e000000-0000-4000-8000-0000000000a1",
      }),
    ).rejects.toBeInstanceOf(NotFoundSignal);
    expect(calls).toEqual([]);
  });

  it("scopes every tenant read to the URL's client, never the cookie's", async () => {
    await renderSection(A, "tech-debt", "overview", {
      service: "5e000000-0000-4000-8000-0000000000a1",
    });
    const scoped = calls.filter((c) => c.clientId !== null);
    expect(scoped.map((c) => c.path)).toEqual(
      expect.arrayContaining([
        "/intake/engagements",
        "/services/5e000000-0000-4000-8000-0000000000a1/stages",
      ]),
    );
    for (const c of scoped) expect(c.clientId).toBe(A);
  });
});

describe("section page: a URL without ?service", () => {
  it("redirects to the one service of that kind", async () => {
    await expect(call(A, "tech-debt", "review")).rejects.toEqual(
      new RedirectSignal(
        `/admin/clients/${A}/services/tech-debt/review?service=5e000000-0000-4000-8000-0000000000a1`,
      ),
    );
  });

  it("lists the services to choose from when there are several", async () => {
    const world = baseWorld();
    world.services.push({
      id: "5e000000-0000-4000-8000-0000000000a2",
      client_id: A,
      kind: "tech_debt",
      status: "draft",
      created_at: "2026-10-01T09:00:00Z",
    });
    calls = installFakeApi(world);
    await renderSection(A, "tech-debt", "review");
    expect(
      screen.getByText(
        "Alpha Corp has 2 Technical Debt Review services. Choose one.",
      ),
    ).toBeInTheDocument();
    expect(
      screen
        .getByRole("link", {
          name: "Technical Debt Review, started 2026-10-01",
        })
        .getAttribute("href"),
    ).toBe(
      `/admin/clients/${A}/services/tech-debt/review?service=5e000000-0000-4000-8000-0000000000a2`,
    );
    expect(screen.queryByTestId("workspace")).toBeNull();
  });

  it("says the kind is not open when the client has none", async () => {
    await renderSection(A, "attack-coverage", "overview");
    expect(
      screen.getByText("MITRE ATT&CK Coverage is not open for this client."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to Alpha Corp" }),
    ).toHaveAttribute("href", `/admin/clients/${A}`);
    expect(screen.queryByTestId("workspace")).toBeNull();
  });

  it("sends a Risk Register section to the Risk Register, which has none yet", async () => {
    await expect(call(A, "risk-register", "overview")).rejects.toEqual(
      new RedirectSignal(`/admin/clients/${A}/services/risk-register`),
    );
  });

  it("does not offer an archived service in the redirect", async () => {
    const world = baseWorld();
    world.services[0].status = "archived";
    calls = installFakeApi(world);
    await renderSection(A, "tech-debt", "overview");
    expect(
      screen.getByText("Technical Debt Review is not open for this client."),
    ).toBeInTheDocument();
  });
});
