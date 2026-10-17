/**
 * #1379: Zero Trust is split, so the page hands the URL's section to the Zero
 * Trust workspace, which renders only that section's blocks. Tested through
 * the page, the surface an admin reaches, not through the slot. Zero Trust has
 * no Inputs section (page plan decision 1), so the page does not offer one.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SECTIONS } from "@/components/service-shell/SectionBar";

import { slugForKind } from "@/components/service-shell/frameRoutes";

import { A, baseWorld, installFakeApi } from "../../../../fake-api.testkit";

const ZT_CISA = "5e000000-0000-4000-8000-0000000000d1";
const ZT_DOD = "5e000000-0000-4000-8000-0000000000d2";

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
  ZtWorkspace: (p: { framework: string; section?: string }) => (
    <div
      data-testid="workspace"
      data-framework={p.framework}
      data-section-prop={p.section ?? "none"}
    >
      zt
    </div>
  ),
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
  const w = baseWorld();
  installFakeApi({
    ...w,
    services: [
      ...w.services,
      {
        id: ZT_CISA,
        client_id: A,
        kind: "zero_trust_cisa",
        status: "in_progress",
        created_at: "2026-09-04T10:00:00Z",
      },
      {
        id: ZT_DOD,
        client_id: A,
        kind: "zero_trust_dod",
        status: "in_progress",
        created_at: "2026-09-05T10:00:00Z",
      },
    ],
  });
});

describe("section page: Zero Trust renders the URL's section (#1379)", () => {
  const ZT_SECTIONS = SECTIONS.map((s) => s.key).filter((k) => k !== "inputs");

  it.each(ZT_SECTIONS)(
    "CISA %s: the workspace is given that section",
    async (key) => {
      await renderSection(slugForKind("zero_trust_cisa"), key, ZT_CISA);
      const ws = screen.getByTestId("workspace");
      expect(ws).toHaveAttribute("data-framework", "cisa_ztmm_2_0");
      expect(ws).toHaveAttribute("data-section-prop", key);
    },
  );

  it.each(ZT_SECTIONS)(
    "DoD %s: the workspace is given that section",
    async (key) => {
      await renderSection(slugForKind("zero_trust_dod"), key, ZT_DOD);
      const ws = screen.getByTestId("workspace");
      expect(ws).toHaveAttribute("data-framework", "dod_ztra");
      expect(ws).toHaveAttribute("data-section-prop", key);
    },
  );

  it("Zero Trust has no Inputs section: the page refuses it", async () => {
    await expect(
      renderSection(slugForKind("zero_trust_cisa"), "inputs", ZT_CISA),
    ).rejects.toThrow();
  });
});
