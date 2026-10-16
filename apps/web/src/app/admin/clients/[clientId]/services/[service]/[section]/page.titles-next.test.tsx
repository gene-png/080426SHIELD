/**
 * T6: each section's tab title, and the service header's "Next:" line, both
 * approved on #736 (issuecomment-6218890818 item 4). The expected strings are
 * transcribed from the approved plan (issuecomment-6218399091), never built
 * from the code's own tables, and everything goes through the page.
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
  TechDebtWorkspace: () => <div data-testid="workspace" />,
}));
vi.mock("@/components/admin/attack/AttackWorkspace", () => ({
  AttackWorkspace: () => <div data-testid="workspace" />,
}));
vi.mock("@/components/admin/csf/CsfWorkspace", () => ({
  CsfWorkspace: () => <div data-testid="workspace" />,
}));
vi.mock("@/components/admin/zt/ZtWorkspace", () => ({
  ZtWorkspace: () => <div data-testid="workspace" />,
}));

import SectionPage, { generateMetadata } from "./page";

function title(service: string, section: string) {
  return generateMetadata({
    params: Promise.resolve({ clientId: A, service, section }),
  });
}

describe("tab titles: {section} · {service}", () => {
  it.each([
    ["tech-debt", "overview", "Overview · Technical Debt Review"],
    ["tech-debt", "inputs", "Inputs · Technical Debt Review"],
    ["tech-debt", "ai-draft", "AI draft · Technical Debt Review"],
    ["tech-debt", "review", "Review · Technical Debt Review"],
    ["tech-debt", "analysis", "Analysis · Technical Debt Review"],
    ["tech-debt", "generate", "Generate · Technical Debt Review"],
    ["tech-debt", "quality-check", "Quality check · Technical Debt Review"],
    [
      "tech-debt",
      "approve-and-release",
      "Approve and release · Technical Debt Review",
    ],
    ["tech-debt", "recommendations", "Recommendations · Technical Debt Review"],
    ["attack-coverage", "review", "Review · MITRE ATT&CK Coverage Mapping"],
    ["csf", "ai-draft", "AI draft · NIST CSF 2.0 Assessment"],
    [
      "zero-trust-cisa",
      "analysis",
      "Analysis · Zero Trust Assessment (CISA ZTMM 2.0)",
    ],
    [
      "zero-trust-dod",
      "approve-and-release",
      "Approve and release · Zero Trust Assessment (DoD ZTRA)",
    ],
  ])("%s / %s reads %s", async (service, section, expected) => {
    expect(await title(service, section)).toEqual({ title: expected });
  });

  it("gives no title to a section the kind does not have (the page is not found)", async () => {
    expect(await title("csf", "inputs")).toEqual({});
    expect(await title("tech-debt", "settings")).toEqual({});
    expect(await title("bogus", "overview")).toEqual({});
  });
});

/** The fake API, with the stages read answering `stages` for every service. */
function serveStages(
  stages: { key: string; state: string }[],
  world = baseWorld(),
): void {
  installFakeApi(world);
  const fake = globalThis.fetch;
  globalThis.fetch = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      const m = /^\/services\/([^/]+)\/stages$/.exec(path);
      if (!m) return fake(input, init);
      const real = await fake(input, init);
      if (!real.ok) return real;
      const body = (await real.json()) as Record<string, unknown>;
      return new Response(JSON.stringify({ ...body, stages }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    },
  ) as unknown as typeof fetch;
}

const KEYS = ["prepare", "analyze", "review", "approve", "generate", "release"];
function at(current: string | null) {
  const i = current === null ? KEYS.length : KEYS.indexOf(current);
  return KEYS.map((key, j) => ({
    key,
    state: j < i ? "complete" : j === i ? "current" : "pending",
  }));
}

async function renderSection(
  service: string,
  serviceId: string,
): Promise<void> {
  render(
    await SectionPage({
      params: Promise.resolve({ clientId: A, service, section: "overview" }),
      searchParams: Promise.resolve({ service: serviceId }),
    }),
  );
}

function hrefTo(service: string, section: string, id: string): string {
  return `/admin/clients/${A}/services/${service}/${section}?service=${id}`;
}

beforeEach(() => {
  installFakeApi(baseWorld());
});

describe("the header's Next: line, from the current stage", () => {
  it.each([
    ["prepare", "Next: add the inputs", "inputs"],
    ["analyze", "Next: run the AI draft", "ai-draft"],
    ["review", "Next: review and approve the AI draft", "review"],
    // The API never makes `approve` current today (derive_stages sets
    // reviewed = approved); the approved line is pinned for when it does.
    ["approve", "Next: approve the assessment", "approve-and-release"],
    ["generate", "Next: generate the deliverable", "generate"],
    ["release", "Next: release to the client", "approve-and-release"],
  ])("Tech Debt at %s: %s, linking to %s", async (stage, line, section) => {
    serveStages(at(stage));
    await renderSection("tech-debt", TD_A);
    const next = screen.getByTestId("service-header-next");
    expect(next.textContent).toBe(line);
    expect(screen.getByRole("link", { name: line.slice(6) })).toHaveAttribute(
      "href",
      hrefTo("tech-debt", section, TD_A),
    );
  });

  it("CSF at prepare waits for the client, linking to Overview", async () => {
    serveStages(at("prepare"));
    await renderSection("csf", CSF_A);
    const line = "Next: wait for the client's self-assessment";
    expect(screen.getByTestId("service-header-next").textContent).toBe(line);
    expect(screen.getByRole("link", { name: line.slice(6) })).toHaveAttribute(
      "href",
      hrefTo("csf", "overview", CSF_A),
    );
  });

  it.each([
    [
      "zero_trust_cisa",
      "zero-trust-cisa",
      "5e000000-0000-4000-8000-0000000000e1",
    ],
    [
      "zero_trust_dod",
      "zero-trust-dod",
      "5e000000-0000-4000-8000-0000000000f1",
    ],
  ] as const)(
    "Zero Trust (%s) at prepare waits for the client, linking to Overview",
    async (kind, slug, id) => {
      const world = baseWorld();
      world.services.push({
        id,
        client_id: A,
        kind,
        status: "draft",
        created_at: "2026-09-04T10:00:00Z",
      });
      serveStages(at("prepare"), world);
      await renderSection(slug, id);
      const line = "Next: wait for the client's self-assessment";
      expect(screen.getByTestId("service-header-next").textContent).toBe(line);
      expect(screen.getByRole("link", { name: line.slice(6) })).toHaveAttribute(
        "href",
        hrefTo(slug, "overview", id),
      );
    },
  );

  it("CSF past prepare uses the shared line (no Inputs section to link)", async () => {
    serveStages(at("analyze"));
    await renderSection("csf", CSF_A);
    expect(screen.getByTestId("service-header-next").textContent).toBe(
      "Next: run the AI draft",
    );
  });

  it("shows no Next: line when every stage is complete", async () => {
    serveStages(at(null));
    await renderSection("tech-debt", TD_A);
    // The header rendered (positive state first), and carries no Next: line.
    expect(screen.getByTestId("service-header-version")).toBeVisible();
    expect(screen.queryByTestId("service-header-next")).toBeNull();
  });
});
