/**
 * T6: the section page hands the URL's section to the workspace slot, the one
 * place that decides what a section renders, so a service track can split its
 * components there. Until a track does, every section shows the whole
 * existing workspace, once. Tested through the page, not the slot.
 */
import { render, screen, within } from "@testing-library/react";
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
  TechDebtWorkspace: (p: { serviceId: string }) => (
    <div data-testid="workspace">tech_debt {p.serviceId}</div>
  ),
}));
vi.mock("@/components/admin/attack/AttackWorkspace", () => ({
  AttackWorkspace: () => <div data-testid="workspace">attack</div>,
}));
vi.mock("@/components/admin/csf/CsfWorkspace", () => ({
  CsfWorkspace: (p: { serviceId: string }) => (
    <div data-testid="workspace">csf {p.serviceId}</div>
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

describe("section page: the section reaches the workspace slot", () => {
  it.each(SECTIONS.map((s) => s.key))(
    "Tech Debt %s: the slot names that section and holds the whole workspace once",
    async (key) => {
      await renderSection("tech-debt", key, TD_A);
      const slot = screen.getByTestId("section-view");
      expect(slot).toHaveAttribute("data-section", key);
      expect(within(slot).getAllByTestId("workspace")).toHaveLength(1);
      expect(within(slot).getByTestId("workspace")).toHaveTextContent(
        `tech_debt ${TD_A}`,
      );
    },
  );

  it("CSF ai-draft: the slot names ai-draft", async () => {
    await renderSection("csf", "ai-draft", CSF_A);
    const slot = screen.getByTestId("section-view");
    expect(slot).toHaveAttribute("data-section", "ai-draft");
    expect(within(slot).getByTestId("workspace")).toHaveTextContent(
      `csf ${CSF_A}`,
    );
  });
});
