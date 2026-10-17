/**
 * #1376: Tech Debt is split, so the page hands the URL's section to the Tech
 * Debt workspace, which renders only that section's blocks. Tested through
 * the page, the surface an admin reaches, not through the slot.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SECTIONS } from "@/components/service-shell/SectionBar";

import { A, baseWorld, installFakeApi } from "../../../../fake-api.testkit";

const TD_A = "5e000000-0000-4000-8000-0000000000a1";
const CSF_A = "5e000000-0000-4000-8000-0000000000c1";

vi.mock("@/lib/auth/options", () => ({
  auth: async () => ({ role: "admin", accessToken: "tok" }),
}));
vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => undefined }),
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
  TechDebtWorkspace: (p: { serviceId: string; section?: string }) => (
    <div data-testid="workspace" data-section-prop={p.section ?? "none"}>
      tech_debt {p.serviceId}
    </div>
  ),
}));
vi.mock("@/components/admin/attack/AttackWorkspace", () => ({
  AttackWorkspace: () => <div data-testid="workspace">attack</div>,
}));
vi.mock("@/components/admin/csf/CsfWorkspace", () => ({
  CsfWorkspace: (p: { serviceId: string; section?: string }) => (
    <div data-testid="workspace" data-section-prop={p.section ?? "none"}>
      csf {p.serviceId}
    </div>
  ),
}));
vi.mock("@/components/admin/zt/ZtWorkspace", () => ({
  ZtWorkspace: () => <div data-testid="workspace">zt</div>,
}));

import SectionPage from "./page";

async function renderSection(
  service: string,
  section: string,
  serviceId: string,
): Promise<void> {
  render(
    await SectionPage({
      params: Promise.resolve({ clientId: A, service, section }),
      searchParams: Promise.resolve({ service: serviceId }),
    }),
  );
}

beforeEach(() => {
  installFakeApi(baseWorld());
});

describe("section page: Tech Debt renders the URL's section (#1376)", () => {
  it.each(SECTIONS.map((s) => s.key))(
    "Tech Debt %s: the workspace is given that section",
    async (key) => {
      await renderSection("tech-debt", key, TD_A);
      expect(screen.getByTestId("workspace")).toHaveAttribute(
        "data-section-prop",
        key,
      );
    },
  );

  it("CSF is not split yet: its workspace is given no section", async () => {
    await renderSection("csf", "ai-draft", CSF_A);
    expect(screen.getByTestId("workspace")).toHaveAttribute(
      "data-section-prop",
      "none",
    );
  });
});
